from gevent import monkey; monkey.patch_all()
# inject the lib folder before everything else
import os
import sys
from waitlist.permissions import perm_manager
from waitlist.utility.settings.settings import sget_insert
from waitlist.blueprints.options.inserts import bp
from waitlist.data.names import WTMRoles
base_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_path, 'lib'))
from pycrest.eve import EVE
from waitlist.utility.settings import settings
from waitlist.utility.config import debug_enabled, debug_fileversion,\
    crest_client_id, crest_client_secret, crest_return_url
from waitlist.data.version import version
from waitlist.utility.eve_id_utils import get_account_from_db, get_char_from_db,\
    is_char_banned, get_character_by_id_and_name, get_character_by_name
from datetime import datetime
import math
from sqlalchemy.exc import StatementError
from waitlist.utility import config
from logging.handlers import TimedRotatingFileHandler
from waitlist.blueprints.feedback import feedback
from gevent.pywsgi import WSGIServer
from waitlist.base import app, login_manager, db
from flask_login import login_required, current_user, login_user,\
    logout_user
import logging
from waitlist.storage.database import Account, WaitlistEntry,\
    Character, WaitlistGroup, TeamspeakDatum
from flask_principal import RoleNeed, identity_changed, Identity, AnonymousIdentity,\
    identity_loaded, UserNeed
from waitlist.data.perm import perm_management, perm_settings, perm_admin,\
    perm_officer, perm_accounts, perm_feedback, perm_dev, perm_leadership,\
    perm_bans, perm_viewfits, perm_comphistory, perm_mod_mail_resident,\
    perm_mod_mail_tbadge
from flask.templating import render_template
from waitlist.blueprints.settings import bp_settings
from waitlist.blueprints.fittings import bp_waitlist
from flask.globals import request, current_app
import flask
from werkzeug.utils import redirect
from flask.helpers import url_for
from waitlist.utility.utils import is_igb
from waitlist.blueprints.fc_sso import bp as fc_sso_bp, get_sso_redirect,\
    add_sso_handler
from waitlist.blueprints.fleet import bp as fleet_bp
from waitlist.blueprints.api.fleet import bp as api_fleet_bp
from waitlist.blueprints.api.fittings import bp as api_wl_bp
from waitlist.blueprints.api.teamspeak import bp as api_ts3_bp
from waitlist.blueprints.options.mail import bp as settings_mail_bp
from waitlist.blueprints.options.fleet_motd import bp as fmotd_bp
from waitlist.blueprints.reform import bp as bp_fleet_reform
from waitlist.blueprints.history.comphistory import bp as bp_comphistory_search
from waitlist.blueprints.api.history import bp as bp_api_history
from waitlist.blueprints.options.inserts import bp as bp_inserts

app.register_blueprint(bp_waitlist)
app.register_blueprint(bp_settings, url_prefix='/settings')
app.register_blueprint(feedback, url_prefix="/feedback")
app.register_blueprint(fc_sso_bp, url_prefix="/fc_sso")
app.register_blueprint(fleet_bp, url_prefix="/fleet")
app.register_blueprint(api_fleet_bp, url_prefix="/api/fleet")
app.register_blueprint(api_wl_bp, url_prefix="/api/fittings")
app.register_blueprint(api_ts3_bp, url_prefix="/api/ts3")
app.register_blueprint(settings_mail_bp, url_prefix="/settings/mail")
app.register_blueprint(fmotd_bp, url_prefix="/settings/fmotd")
app.register_blueprint(bp_fleet_reform, url_prefix="/fleet/reform")
app.register_blueprint(bp_comphistory_search, url_prefix="/history/comp_search")
app.register_blueprint(bp_api_history, url_prefix="/api/history")
app.register_blueprint(bp_inserts, url_prefix="/settings/inserts")

logger = logging.getLogger(__name__)

# set if it is the igb
@app.context_processor
def inject_data():
    is_account = False
    if hasattr(current_user, 'type'):
        is_account=(current_user.type == "account")
    if debug_enabled:
        display_version = debug_fileversion
    else:
        display_version = version
    header_insert = sget_insert('header')
    if (header_insert is not None):
        header_insert = header_insert.replace("$type$", str(get_user_type()))
    return dict(is_igb=is_igb(), perm_admin=perm_admin,
                perm_settings=perm_settings, perm_man=perm_management,
                perm_officer=perm_officer, perm_accounts=perm_accounts,
                perm_feedback=perm_feedback, is_account=is_account,
                perm_dev=perm_dev, perm_leadership=perm_leadership, perm_bans=perm_bans,
                perm_viewfits=perm_viewfits, version=display_version, perm_comphistory=perm_comphistory,
                perm_res_mod=perm_mod_mail_resident, perm_t_mod=perm_mod_mail_tbadge, perm_manager=perm_manager,
                header_insert=header_insert
                )

def get_user_type():
    #0=linemember,1=fc/t,2=lm/r,3=both
    val = -1
    if current_user.is_authenticated:
        val = 0
        if current_user.type == "account":
            is_lm = False
            is_fc = False
            for role in current_user.roles:
                if (role.name == WTMRoles.fc or role.name == WTMRoles.tbadge):
                    is_fc = True
                    if (is_lm):
                        break
                elif (role.name == WTMRoles.lm or role.name == WTMRoles.resident):
                    is_lm = True
                    if (is_fc):
                        break
            if is_fc:
                val += 1
            if is_lm:
                val += 2
    return val

@app.before_request
def check_ban():
    if current_user.is_authenticated:
        if current_user.type == "character":
            is_banned, _ = is_char_banned(current_user)
            if is_banned:
                force_logout()
            else:
                # check if character has right charid in header, since clients seem to share ids
                # this could be used to detect multiboxers actually
                if is_igb(): # should allways be if he is char authenticated, but well lets check again
                    char_id_str = request.headers.get('Eve-Charid')
                    if char_id_str is None: # he was logged in with other account and no trust on this
                        force_logout()
                        return
                    char_id = int(char_id_str)
                    if current_user.get_eve_id() != char_id:
                        force_logout()
        elif current_user.type == "account":
            if current_user.disabled:
                force_logout()
            

def force_logout():
    logout_user()
    for key in ('identity.name', 'identity.auth_type'):
        flask.globals.session.pop(key, None)

    # Tell Flask-Principal the user is anonymous
    identity_changed.send(current_app._get_current_object(),
                          identity=AnonymousIdentity())

@app.route('/', methods=['GET'])
@login_required
def index():
    if 'groupId' in request.args:
        group_id = int(request.args.get('groupId'))
        group = db.session.query(WaitlistGroup).get(group_id)
    else:
        group = db.session.query(WaitlistGroup).filter(WaitlistGroup.enabled == True).order_by(WaitlistGroup.odering).first()
    
    if group == None:
        return render_template("index.html", is_index=True)
    
    new_bro = True
    if current_user.type == "character":
        if current_user.newbro == None:
            new_bro = True
        else:
            new_bro = current_user.newbro
    elif current_user.type == "account":
        if current_user.current_char_obj.newbro == None:
            new_bro = True
        else:
            new_bro = current_user.current_char_obj.newbro
    
    wlists = []
    logi_wl = group.logilist
    dps_wl = group.dpslist
    sniper_wl = group.sniperlist
    queue = group.xuplist
    other_wl = group.otherlist

    wlists.append(queue)
    wlists.append(logi_wl)
    wlists.append(dps_wl)
    wlists.append(sniper_wl)
    if (other_wl is not None):
        wlists.append(other_wl)
    
    activegroups = db.session.query(WaitlistGroup).filter(WaitlistGroup.enabled == True).all()
    active_ts_setting_id = settings.sget_active_ts_id()
    active_ts_setting = None
    if active_ts_setting_id is not None:
        active_ts_setting = db.session.query(TeamspeakDatum).get(active_ts_setting_id)
    
    return render_template("index.html", lists=wlists, user=current_user, is_index=True, is_on_wl=is_on_wl(), newbro=new_bro, group=group, groups=activegroups, ts=active_ts_setting)

def is_on_wl():
    eveId = current_user.get_eve_id();
    entry = db.session.query(WaitlistEntry).filter(WaitlistEntry.user == eveId).first();
    return (entry is not None)

@app.route("/help", methods=["GET"])
def site_help():
    return render_template("help.html")

@login_manager.user_loader
def load_user(unicode_id):
    # it is an account
    try:
        return get_user_from_db(unicode_id)
    except StatementError:
        db.session.rollback()
        logger.exception("Failed to get user from db")
        return get_user_from_db(unicode_id)

def get_user_from_db(unicode_id):
    if unicode_id.startswith("acc"):
        unicode_id = unicode_id.replace("acc", "", 1)
        return get_account_from_db(int(unicode_id))
    
    if unicode_id.startswith("char"):
        unicode_id = unicode_id.replace("char", "", 1)
        return get_char_from_db(int(unicode_id))
    
    return None

# callable like /tokenauth?token=359th8342rt0f3uwf0234r
@app.route('/tokenauth')
def login_token():
    login_token = request.args.get('token');
    user = db.session.query(Account).filter(Account.login_token == login_token).first()

    # token was not found
    if user == None:
        return flask.abort(401);
    
    if user.disabled:
        return flask.abort(403)
    
    logger.info("Got User %s", user)
    login_user(user);
    logger.info("Logged in User %s", user)

    # notify principal extension
    identity_changed.send(current_app._get_current_object(),
                                  identity=Identity(user.id))

    return redirect(url_for('index'), code=303)

@app.route("/charauth")
def char_auth():
    token = request.args.get('token')
    logger.info("Token %s", token)
    character = db.session.query(Character).filter(Character.login_token == token).first()
    # token was not found
    if character == None:
        return flask.abort(401);
    logger.info("Got User %s", character)
    login_user(character);
    logger.info("Logged in User %s", character)

    # notify principal extension
    identity_changed.send(current_app._get_current_object(),
                                  identity=Identity(character.id))

    return redirect(url_for('index'), code=303)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    
    for key in ('identity.name', 'identity.auth_type'):
        flask.globals.session.pop(key, None)

    # Tell Flask-Principal the user is anonymous
    identity_changed.send(current_app._get_current_object(),
                          identity=AnonymousIdentity())

    return render_template("logout.html")

@identity_loaded.connect_via(app)
def on_identity_loaded(sender, identity):
    # Set the identity user object
    identity.user = current_user
    # Add the UserNeed to the identity
    logger.info("loading identity for %s", current_user)
    if hasattr(current_user, 'id'):
        identity.provides.add(UserNeed(current_user.id))


    if hasattr(current_user, "type"):  # it is a custom user class
        if current_user.type == "account":  # it is an account, so it can have roles
            account = db.session.query(Account).filter(Account.id == current_user.id).first()
            for role in account.roles:
                logger.info("Add role %s", role.name)
                identity.provides.add(RoleNeed(role.name))

@login_manager.unauthorized_handler
def unauthorized():
    '''
    FC should have a login token, that always going stay the same
    additionally they are going to have login form
    
    if we have igb headers,
        if the user has no roles or only one of the flowing:
            log them in by header
        else
            Redirect them to SSO login
    else:
        Redirect to SSO login
        // here the user has the ability to activate trust and get logged in on the next request by headers
        then check them and try to log the user in
        ONLY users with no roles ore the following '' are allowed to login by headers
       
    TODO: Implement 
    '''

    # if we have a igb check if we are trusted!
    if is_igb():
        return unauthorized_igb()
    
    return unauthorized_ogb()

def unauthorized_igb():
    """
    Handle unauthroized users that visit from the ingame browser
    """
    TRUSTED_HEADER = "Eve-Trusted"
    # TRUESTED_HEADER_NO = "No"
    TRUESTED_HEADER_YES = "Yes"
    
    is_trusted = False
    trused_header_value = request.headers.get(TRUSTED_HEADER)

    if trused_header_value == TRUESTED_HEADER_YES:
        is_trusted = True

    if (is_trusted):
        return unauth_igb_trusted()
    
    return unauth_igb_untrused()

def unauth_igb_trusted():
    """
    Handle users with igb that trusted us
    -> try to authorize them by headers, if they are not restricted
    """
    char_id_str = request.headers.get('Eve-Charid')
    if char_id_str == None:
        logger.debug("Getting char id from headers failed")
        return flask.abort(400)

    char_id = int(char_id_str)
    char_name = request.headers.get('Eve-Charname')
    char = get_character_by_id_and_name(char_id, char_name)
    is_banned, reason = is_char_banned(char)
    if is_banned:
        return flask.abort(401, 'You are banned, because your '+reason+" is banned!")

    login_user(char, remember=True)
    logger.debug("Getting char id from headers succeeded.")
    return redirect(request.url)

def unauth_igb_untrused():
    """
    Send message to enable trust
    """
    return render_template("enable_trust.html")

def unauthorized_ogb():
    """
    Handle unauthorized users that visit with an out of game browser
    -> Redirect them to SSO
    """
    return get_sso_redirect('linelogin', '')

def member_login_cb(code):
    eve = EVE(client_id=crest_client_id, api_key=crest_client_secret, redirect_uri=crest_return_url)
    con = eve.authorize(code)
    authInfo = con.whoami()
    charID = authInfo['CharacterID']
    charName = authInfo['CharacterName']
    if charID is None or charName is None:
        flask.abort(400, "Getting Character from AuthInformation Failed!")
    
    char = get_character_by_id_and_name(charID, charName)
    is_banned, reason = is_char_banned(char)
    if is_banned:
        return flask.abort(401, 'You are banned, because your '+reason+" is banned!")

    login_user(char, remember=True)
    logger.debug("Member Login by %s successful", char.get_eve_name())
    return redirect(url_for("index"))

add_sso_handler('linelogin', member_login_cb)

@app.route("/update_token")
@login_required
@perm_admin.require(http_exception=401)
def create_char_logintoken():
    username = request.args.get('char')

    eve_char = get_character_by_name(username)
    token = eve_char.get_login_token()
    db.session.commit()
    return token

@app.template_filter('waittime')
def jinja2_waittime_filter(value):
    currentUTC = datetime.utcnow()
    waitedTime = currentUTC-value
    return str(int(math.floor(waitedTime.total_seconds()/60)))

if __name__ == '__main__':
    err_fh = TimedRotatingFileHandler(filename=config.error_log, when="midnight", interval=1, utc=True)
    info_fh = TimedRotatingFileHandler(filename=config.info_log, when="midnight", interval=1, utc=True)
    access_fh = TimedRotatingFileHandler(filename=config.access_log, when="midnight", interval=1, utc=True)
    debug_fh = TimedRotatingFileHandler(filename=config.debug_log, when="midnight", interval=1, utc=True)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(pathname)s - %(funcName)s - %(lineno)d - %(message)s')
    err_fh.setFormatter(formatter)
    info_fh.setFormatter(formatter)
    access_fh.setFormatter(formatter)
    debug_fh.setFormatter(formatter)

    info_fh.setLevel(logging.INFO)
    err_fh.setLevel(logging.ERROR)
    debug_fh.setLevel(logging.DEBUG)

    waitlistlogger = logging.getLogger("waitlist")
    waitlistlogger.addHandler(err_fh)
    waitlistlogger.addHandler(info_fh)
    waitlistlogger.addHandler(debug_fh)
    waitlistlogger.setLevel(logging.DEBUG)

    app.logger.addHandler(err_fh)
    app.logger.addHandler(info_fh)
    app.logger.addHandler(debug_fh)
    app.logger.setLevel(logging.INFO)
    
    wsgi_logger = logging.getLogger("gevent.pywsgi.WSGIServer")
    wsgi_logger.addHandler(err_fh)
    wsgi_logger.addHandler(access_fh)
    wsgi_logger.setLevel(logging.INFO)
    
    
    
    pycrest_logger = logging.getLogger("pycrest.eve")
    pycrest_logger.addHandler(debug_fh)
    pycrest_logger.addHandler(info_fh)
    pycrest_logger.addHandler(err_fh)
    pycrest_logger.setLevel(logging.DEBUG)
    
    #app.run(host="0.0.0.0", port=81, debug=True)
    server = WSGIServer((config.server_bind, config.server_port), app, log=wsgi_logger, error_log=wsgi_logger)
    server.serve_forever()
