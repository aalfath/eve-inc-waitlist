from typing import Optional, Tuple

from esipy import EsiClient

from waitlist.utility import outgate
from waitlist.storage.database import Constellation, SolarSystem, Station,\
    InvType, Account, Character, Ban, Whitelist
from waitlist import db
import logging

from waitlist.utility.swagger import get_api
from waitlist.utility.swagger.eve import get_esi_client
from waitlist.utility.swagger.eve.search import SearchEndpoint, SearchResponse

logger = logging.getLogger(__name__)


def get_constellation(name: str) -> Constellation:
    return db.session.query(Constellation).filter(Constellation.constellationName == name).first()


def get_system(name: str) -> SolarSystem:
    return db.session.query(SolarSystem).filter(SolarSystem.solarSystemName == name).first()


def get_station(name: str) -> Station:
    return db.session.query(Station).filter(Station.stationName == name).first()


def get_item_id(name: str) -> int:
    logger.debug("Getting id for item %s", name)
    item = db.session.query(InvType).filter(InvType.typeName == name).first()
    if item is None:
        item_data = get_item_data_from_api(name)
        if item_data is None:
            return -1

        # add the type to db
        market_group_id = None

        if hasattr(item_data, 'market_group_id'):
            market_group_id = item_data.market_group_id
        item = InvType(typeID=item_data.type_id, groupID=item_data.group_id,
                       typeName=item_data.name, description=item_data.description,
                       marketGroupID=market_group_id)

        db.session.merge(item)
        db.session.commit()
        logger.info(f'Added new {item}')
        return item.typeID

    return item.typeID


def get_item_data_from_api(name: str) -> Optional[any]:
    """Tries to get api data of an item with this name from Search API"""
    search_endpoint = SearchEndpoint()
    search_response: SearchResponse = search_endpoint.public_search(name, ['inventory_type'], True)
    result_ids = search_response.inventory_type_ids()
    if result_ids is None or len(result_ids) < 1:
        return None

    esi_client: EsiClient = get_esi_client(True)
    api = get_api()

    for result_id in result_ids:
        type_result = esi_client.request(api.op['get_universe_types_type_id'](type_id=result_id))
        if type_result.data.name == name:
            return type_result.data

    return None




# load an account by its id
def get_account_from_db(int_id: int) -> Account:
    return db.session.query(Account).filter(Account.id == int_id).first()


# load a character by its id
def get_char_from_db(int_id: int) -> Character:
    return db.session.query(Character).filter(Character.id == int_id).first()


def create_new_character(eve_id: int, char_name: str) -> Character:
    char = Character()
    char.id = eve_id
    char.eve_name = char_name
    char.newbro = True
    db.session.add(char)
    db.session.commit()
    return char


def get_character_by_id_and_name(eve_id: int, eve_name: str) -> Character:
    char = get_char_from_db(eve_id)
    if char is None:
        logger.info("No character found for id %d", eve_id)
        # create a new char
        char = create_new_character(eve_id, eve_name)

    return char


def is_charid_banned(character_id: int) -> bool:
    if character_id == 0:  # this stands for no id in the eve api (for example no alliance)
        return False
    return db.session.query(Ban).filter(Ban.id == character_id).count() == 1


def is_charid_whitelisted(character_id: int) -> bool:
    if character_id == 0:
        return False
    return db.session.query(Whitelist).filter(Whitelist.characterID == character_id).count() == 1


def get_character_by_name(eve_name: str) -> Optional[Character]:
    eve_info = outgate.character.get_info_by_name(eve_name)
    if eve_info is None:
        return None
    return get_character_by_id_and_name(eve_info.id, eve_name)


def is_char_banned(char: Character) -> Tuple[bool, str]:
    try:
        corp_id, alli_id = outgate.character.get_affiliations(char.get_eve_id())
        # if he is on whitelist let him pass
        
        char_banned = char.banned
        corp_banned = is_charid_banned(corp_id)
        alli_banned = is_charid_banned(alli_id)
        
        if is_charid_whitelisted(char.get_eve_id()):
            return False, ""
        
        if char_banned:
            return True, "Character"
        
        if is_charid_whitelisted(corp_id):
                return False, ""
        
        if corp_banned:
            return True, "Corporation"
        
        if is_charid_whitelisted(alli_id):
                return False, ""
        
        if alli_banned:
            return True, "Alliance"
        
        return False, ""
    except Exception:
        logger.error("Failed to check if %d was banned", char.get_eve_id(), exc_info=1)
        return False, ""
