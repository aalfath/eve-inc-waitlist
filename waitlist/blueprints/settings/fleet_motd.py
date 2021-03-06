from flask_login import login_required

from waitlist.blueprints.settings import add_menu_entry
from flask.templating import render_template

from waitlist.permissions import perm_manager
from waitlist.utility.settings import sget_motd_hq, sget_motd_vg,\
    sset_motd_hq, sset_motd_vg
from flask.blueprints import Blueprint
import logging
from flask.globals import request
from flask.helpers import flash, url_for
from werkzeug.utils import redirect
bp = Blueprint('settings_fmotds', __name__)
logger = logging.getLogger(__name__)


perm_manager.define_permission('change_fleet_motd')


def get_permission():
    return perm_manager.get_permission('change_fleet_motd')

perm = get_permission()


@bp.route("/")
@login_required
@perm.require()
def index():
    motds = {
        'hq': sget_motd_hq(),
        'vg': sget_motd_vg()
        }
    return render_template("settings/fleet_motd/index.html", motds=motds)


@bp.route("/change/<string:type_>", methods=["POST"])
@login_required
@perm.require()
def change(type_):
    if type_ == "hq":
        motd = request.form.get('motd')
        sset_motd_hq(motd)
        flash("HQ MOTD Saved")
    elif type_ == "vg":
        motd = request.form.get('motd')
        sset_motd_vg(motd)
        flash("VG MOTD Saved")
    return redirect(url_for('settings_fmotds.index'))

add_menu_entry('settings_fmotds.index', 'Fleet MOTD', perm.can)
