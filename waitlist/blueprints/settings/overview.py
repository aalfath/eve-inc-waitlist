import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from flask import Blueprint
from flask import render_template
from flask_login import login_required
from gevent import Greenlet
from sqlalchemy import and_, or_, func

from waitlist import db
from waitlist.blueprints.settings import add_menu_entry
from waitlist.permissions import perm_manager
from waitlist.storage.database import InvType, Character, Shipfit, HistoryEntry, HistoryFits, Account

bp = Blueprint('settings_overview', __name__)
logger = logging.getLogger(__name__)


perm_manager.define_permission('settings_access')

perm_access = perm_manager.get_permission('settings_access')


class StatCache(object):
    def __init__(self) -> None:
        self.__data: Dict[str, Any] = {}

    def has_cache_item(self, key: str) -> bool:
        if key not in self.__data:
            return False

        if self.__data[key]['datetime'] < datetime.utcnow():
            return False
        return True

    def get_cache_item(self, key: str) -> Any:
        if key not in self.__data:
            return None
        return self.__data[key]

    def add_item_to_cache(self, key: str, item: Any) -> None:
        self.__data[key] = item

__cache = StatCache()


@bp.route("/")
@login_required
@perm_access.require(http_exception=401)
def overview():


    # EXTRACT(EPOCH FROM current_timestamp-somedate)/3600

    ship_stats15_days = __get_query_result('shipStats', query_wrapper(query_ship_stats, timedelta(days=30)), 2, 3600)
    approved_fits_by_fc_result = __get_query_result('approvedFits30Days', query_wrapper(query_approved_ships, timedelta(days=7)), 2, 3600)
    ship_stats1_day = __get_query_result('shipStats1Day', query_wrapper(query_ship_stats, timedelta(days=1)), 2, 3600)

    stats = [
        __create_table_cell_row(
            __create_table_cell_data('Top 15 approved distinct Hull/Character combinations last 30 days',
                                     ['Hull', 'Amount'], ship_stats15_days),
            __create_table_cell_data('15 Most Active Command Core Members over last 7days',
                                     ['Account Name', 'Amount'], approved_fits_by_fc_result, [False, True])
        ),
        __create_table_cell_row(
            __create_table_cell_data('Top 15 approved distinct Hull/Character combinations last 24 hours',
                                     ['Hull', 'Amount'], ship_stats1_day),
            __create_table_cell_data('If you have ideas for other stats, use the feedback function.', [], [], [])
        )
    ]

    return render_template('settings/overview.html', stats=stats)


def query_wrapper(func, duration):
    def f():
        return func(duration)
    return f


def query_ship_stats(duration: timedelta):
    '''
    SELECT shipType, COUNT(name)
    FROM (
        SELECT DISTINCT invtypes."typeName" AS "shipType", characters.eve_name AS name
        FROM fittings
        JOIN invtypes ON fittings.ship_type = invtypes."typeID"
        JOIN comp_history_fits ON fittings.id = comp_history_fits."fitID"
        JOIN comp_history ON comp_history_fits."historyID" = comp_history."historyID"
        JOIN characters ON comp_history."targetID" = characters.id
        WHERE
         (
         comp_history.action = 'comp_mv_xup_etr'
         OR
         comp_history.action = 'comp_mv_xup_fit'
         )
        AND DATEDIFF(NOW(),comp_history.time) < 30
    ) AS temp
    GROUP BY "shipType"
    ORDER BY COUNT(name) DESC
    LIMIT 15;
    '''
    since: datetime = datetime.utcnow() - duration

    shiptype_name_combinations = db.session.query(InvType.typeName.label('shipType'), Character.eve_name.label('name')) \
        .distinct() \
        .join(Shipfit, InvType.typeID == Shipfit.ship_type) \
        .join(HistoryFits, Shipfit.id == HistoryFits.fitID) \
        .join(HistoryEntry, HistoryFits.historyID == HistoryEntry.historyID) \
        .join(Character, HistoryEntry.targetID == Character.id) \
        .filter(
            and_(
                or_(
                    HistoryEntry.action == 'comp_mv_xup_etr',
                    HistoryEntry.action == 'comp_mv_xup_fit'
                ),
                HistoryEntry.time >= since
            )
        ).subquery('shiptypeNameCombinations')

    return db.session.query(shiptype_name_combinations.c.shipType, func.count(shiptype_name_combinations.c.name)) \
            .group_by(shiptype_name_combinations.c.shipType) \
            .order_by(func.count(shiptype_name_combinations.c.name).desc()) \
            .limit(15) \
            .all()


def query_approved_ships(duration: timedelta):
    '''
    SELECT name, COUNT(fitid)
    FROM (
        SELECT DISTINCT accounts.username AS name, comp_history_fits.id as fitid
        FROM fittings
        JOIN invtypes ON fittings.ship_type = invtypes."typeID"
        JOIN comp_history_fits ON fittings.id = comp_history_fits."fitID"
        JOIN comp_history ON comp_history_fits."historyID" = comp_history."historyID"
        JOIN accounts ON comp_history."sourceID" = accounts.id
        JOIN characters ON comp_history."targetID" = characters.id
        WHERE
         (
         comp_history.action = 'comp_mv_xup_etr'
         OR
         comp_history.action = 'comp_mv_xup_fit'
         )
        AND DATEDIFF(NOW(),comp_history.time) < since
    ) AS temp
    GROUP BY name
    ORDER BY COUNT(fitid) DESC
    LIMIT 15;
    '''
    since: datetime = datetime.utcnow() - duration

    fits_flown_by_subquery = db.session.query(Account.username.label('name'), HistoryFits.id.label('fitid')) \
        .join(HistoryEntry, Account.id == HistoryEntry.sourceID) \
        .join(Character, HistoryEntry.targetID == Character.id) \
        .join(HistoryFits, HistoryEntry.historyID == HistoryFits.historyID) \
        .join(Shipfit, HistoryFits.fitID == Shipfit.id) \
        .join(InvType, Shipfit.ship_type == InvType.typeID) \
        .filter(
            and_(
                or_(
                    HistoryEntry.action == 'comp_mv_xup_etr', HistoryEntry.action == 'comp_mv_xup_fit'
                ),
                HistoryEntry.time >= since
            )
        ).subquery("fitsFlownBy")

    return db.session.query(fits_flown_by_subquery.c.name, func.count(fits_flown_by_subquery.c.fitid)) \
            .group_by(fits_flown_by_subquery.c.name) \
            .order_by(func.count(fits_flown_by_subquery.c.fitid).desc()) \
            .limit(15) \
            .all()


def query_shipstats(duration: timedelta):
    since: datetime = datetime.utcnow() - duration

    ship_flown_by_subquery = db.session.query(InvType.typeName.label('shipType'), Character.eve_name.label("name")) \
        .distinct() \
        .join(Shipfit, InvType.typeID == Shipfit.ship_type) \
        .join(HistoryFits, Shipfit.id == HistoryFits.fitID) \
        .join(HistoryEntry, HistoryFits.historyID == HistoryEntry.historyID) \
        .join(Character, HistoryEntry.targetID == Character.id) \
        .filter(
        and_(
            or_(
                HistoryEntry.action == 'comp_mv_xup_etr',
                HistoryEntry.action == 'comp_mv_xup_fit'
            ),
            HistoryEntry.time >= since
            )
        ).subquery('flownBy')
    return db.session.query(ship_flown_by_subquery.c.shipType, func.count(ship_flown_by_subquery.c.name)) \
            .groupe_by(ship_flown_by_subquery.c.shipType) \
            .order_by(func.count(ship_flown_by_subquery.c.name).desc()) \
            .limit(15) \
            .all()


def __create_table_cell_row(left, right):
    return left, right


def __create_table_cell_data(desc, column_names, data, hide_rows=None):
    if hide_rows is None:
        hide_rows = []
    if len(data) >= 1 and len(data[0]) != len(column_names):
        raise ValueError("len(column_names) != len(data[0])")
    if len(hide_rows) == 0:
        hide_rows = [False for _ in range(len(column_names))]
    elif len(hide_rows) != len(column_names):
        raise ValueError("When hide_rows is specified it needs to be of the same length as the defined columns")

    return desc, column_names, data, hide_rows


def __create_cache_item(data: Any, expire_in_s: int):
    return {'data': data, 'datetime': (datetime.utcnow() + timedelta(seconds=expire_in_s))}


def __get_query_result(name, query, column_count, cache_time_seconds):
    if __cache.has_cache_item(name):
        cache_item = __cache.get_cache_item(name)
        result = cache_item['data']
    else:
        # we are going to return this
        cache_item = __cache.get_cache_item(name)
        if cache_item is None:
            result = []
            row = []
            for idx in range(0, column_count):
                row.append('Calculation In Progress...')
            result.append(row)
        else:
            result = cache_item['data']

        # but trigger a recalculation in a greenlet
        def execute_query(data_name, cc, qq, ct):
            db_result = qq()
            if db_result is None:
                __cache.add_item_to_cache(data_name, __create_cache_item([], ct))
                return

            result_ = []
            for db_row in db_result:
                row_list = []
                for idx_cc in range(0, cc):
                    row_list.append(db_row[idx_cc])
                result_.append(row_list)
            __cache.add_item_to_cache(data_name, __create_cache_item(result_, ct))
            db.session.remove()

        Greenlet.spawn(execute_query, name, column_count, query, cache_time_seconds)
    return result

add_menu_entry('settings_overview.overview', 'Overview', lambda: True)
