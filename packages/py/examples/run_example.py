"""Market maker loop for the websocket flow: hold a maker connection open, listen
for RFQs on an asset, price them, and send signed quotes back through the maker
connection.

    RYSK_SDK_PK=<hex private key> \
    RYSK_MAKER=0x<maker address> \
    RYSK_ASSET=0x<asset address> \
    python tests/run_example.py
"""

import asyncio
import json
import os
import signal
import sys
import time

from ryskV12.client import Env, Rysk
from ryskV12.nonce import NonceCounter
from ryskV12.models import (
    Quote,
    Request,
    is_error_data,
    is_json_rpc_response,
    is_quote_notification,
    is_request,
)

PK = os.environ.get("RYSK_SDK_PK", "")
MAKER = os.environ.get("RYSK_MAKER", "")
ASSET = os.environ.get("RYSK_ASSET", "0xb67bfa7b488df4f2efa874f4e59242e9130ae61f")

QUOTE_VALIDITY_SECONDS = 30
# one counter per signing key, shared by quotes and cancels
nonces = NonceCounter(".rysk-nonce")

rysk_sdk = Rysk(env=Env.TESTNET, private_key=PK, v12_cli_path="./ryskV12cli")
# the maker connection; quotes, balances and positions are written into it
maker = None


def price_request(request: Request) -> str:
    """Replace with your own pricing. Quantity and strike come from the request."""
    mid = 4 * 10**18
    edge = 110 if request.isTakerBuy else 90  # sell above, buy below
    return str(mid * edge // 100)


def build_quote(request: Request) -> Quote:
    """The terms have to be the request's - they are what the taker asked for and
    what the signature commits to. Ours are the maker's own fields."""
    return Quote(
        assetAddress=request.asset,
        chainId=request.chainId,
        expiry=request.expiry,
        isPut=request.isPut,
        isTakerBuy=bool(request.isTakerBuy),
        quantity=request.quantity,
        strike=request.strike,
        usd=request.usd,
        collateralAsset=request.collateralAsset,
        maker=MAKER,
        nonce=nonces.next(),
        price=price_request(request),
        validUntil=int(time.time()) + QUOTE_VALIDITY_SECONDS,
        # sent with the quote but not signed; present when the request names one
        premiumAsset=request.premiumAsset,
        # sign against the domain the request asks for, if it asks for one
        domain=request.typeDataDomain,
    )


def quote(request_id: str, request: Request) -> None:
    rysk_sdk.send(maker, rysk_sdk.quote_args(request_id, build_quote(request)))


def handle_maker_message(payload: bytes) -> None:
    text = payload.decode().strip()
    if not text:
        return
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        print("maker:", text)
        return

    # A quote notification tells you where your price stands, so it is the cue to
    # re-quote rather than wait.
    # An error arrives instead of a result, so it has to be read before anything
    # reaches for one.
    if is_json_rpc_response(message) and is_error_data(message.get("error")):
        print(f"maker rpc {message['id']} failed: {message['error']['message']}")
        return
    if is_json_rpc_response(message) and is_quote_notification(message.get("result")):
        result = message["result"]
        print(f"rfq {result['rfqId']}: best {result['newBest']}, yours {result['yours']}")
        return
    print("maker:", text)


def handle_rfq_message(payload: bytes) -> None:
    text = payload.decode().strip()
    if not text:
        return
    try:
        message = json.loads(text)
        if is_json_rpc_response(message) and is_error_data(message.get("error")):
            print(f"rfq rpc {message['id']} failed: {message['error']['message']}")
            return
        if not is_json_rpc_response(message) or not is_request(message.get("result")):
            return
        request = Request.from_json(json.dumps(message["result"]))
        print(f"rfq {message['id']}: {request.quantity} @ {request.strike}")
        quote(message["id"], request)
    except Exception as e:
        print("failed to handle rfq:", e)


async def process_rfqs() -> None:
    global maker
    # The maker connection is what quotes and transfers are written into; it has
    # to stay open for the whole session. Commands sent before the websocket is
    # up wait in its stdin.
    maker = await rysk_sdk.execute_async(rysk_sdk.connect_args("maker"), handle_maker_message)

    # Account reads go through the maker connection like everything else.
    rysk_sdk.send(maker, rysk_sdk.balances_args(MAKER))
    rysk_sdk.send(maker, rysk_sdk.positions_args(MAKER))

    rfq = await rysk_sdk.execute_async(rysk_sdk.connect_args(f"rfqs/{ASSET}"), handle_rfq_message)
    print(f"listening for rfqs on {ASSET}")

    def disconnect():
        maker.terminate()
        rfq.terminate()

    asyncio.get_running_loop().add_signal_handler(signal.SIGINT, disconnect)
    await rfq.wait()
    print("\ndisconnected")


if __name__ == "__main__":
    if not PK or not MAKER:
        print("set RYSK_SDK_PK and RYSK_MAKER", file=sys.stderr)
        sys.exit(1)
    asyncio.run(process_rfqs())
