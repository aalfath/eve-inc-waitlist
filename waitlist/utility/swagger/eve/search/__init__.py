import logging
from esipy import EsiClient

from requests.packages.urllib3.exceptions import ReadTimeoutError
from typing import Sequence, Union

from waitlist.utility.swagger.eve.search.responses import SearchResponse
from waitlist.utility.swagger.eve import get_esi_client, get_expire_time, make_error_response, ESIEndpoint, ESIResponse

logger = logging.getLogger(__name__)


class SearchEndpoint(ESIEndpoint):
    def __init__(self) -> None:
        super().__init__()
        self.esi_client: EsiClient = get_esi_client(True)

    def public_search(self, search: str, type_names: Sequence[str], strict: bool = True)\
            -> Union[SearchResponse, ESIResponse]:

        try:
            resp = self.esi_client.request(self._api().op['get_search'](
                categories=type_names,
                search=search,
                strict=strict
                )
            )
            if resp.status == 200:
                return SearchResponse(get_expire_time(resp), resp.status, None, resp.data)
            else:
                return make_error_response(resp)

        except ReadTimeoutError as e:
            logger.error(f'ESI Read Timeout on public_search {e}')
            raise e
