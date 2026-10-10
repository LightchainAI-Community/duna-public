#!/usr/bin/env python3
"""Build an Ethereum Clearing house to 9200 Clearing house Hyperlane transferRemote paste file."""

import json
import urllib.request
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pathlib import Path

from eth_abi import encode, decode

ETH_SAFE = "0xba69032451D2682b413d18422cef40781af32755"
DEST_SAFE = "0xFc21263493BD8EBD99C8E4A9Fc249A5087A6e047"
ROUTER = "0x01f80bb8e78e79881E8Ec7832fB6C2c59f64e353"
LCAI = "0x9cA8530CA349c966Fe9ef903Df17a75B8A778927"
DESTINATION = 9200
RECIPIENT = "0x000000000000000000000000Fc21263493BD8EBD99C8E4A9Fc249A5087A6e047"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
RPCS = ["https://eth.drpc.org", "https://rpc.mevblocker.io", "https://ethereum-rpc.publicnode.com"]
SAFE_URL = f"https://app.safe.global/home?safe=eth:{ETH_SAFE}"
APPROVE_ABI = '[{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]'
TRANSFER_ABI = '[{"inputs":[{"name":"_destination","type":"uint32"},{"name":"_recipient","type":"bytes32"},{"name":"_amount","type":"uint256"}],"name":"transferRemote","outputs":[{"name":"messageId","type":"bytes32"}],"stateMutability":"payable","type":"function"}]'
PASTE = "Copy and paste values into the transaction builder fields exactly as shown. Replace any ABI data present with what is provided if applicable."
PROXY_NOTE = "Transaction Builder may prompt you to use the proxy ABI or the implementation ABI. Choose proxy ABI, which keeps the address you pasted. Then replace the ABI the tool provides with the ABI below."


def rpc(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for url in RPCS:
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "lcai"})
            result = json.loads(urllib.request.urlopen(req, timeout=20).read())
            if "result" in result:
                return result["result"]
        except Exception:
            continue
    raise RuntimeError("Ethereum RPC call failed. Check the network connection and run again.")


def price_path() -> bytes:
    return (
        bytes.fromhex(LCAI[2:])
        + (3000).to_bytes(3, "big")
        + bytes.fromhex(WETH[2:])
        + (500).to_bytes(3, "big")
        + bytes.fromhex(USDC[2:])
    )


def lcai_for_usd(target: Decimal) -> Decimal:
    data = "0xcdca1753" + encode(["bytes", "uint256"], [price_path(), 1000 * 10**18]).hex()
    quoted = decode(["uint256"], bytes.fromhex(rpc("eth_call", [{"to": QUOTER, "data": data}, "latest"])[2:66]))[0]
    price = Decimal(quoted) / Decimal(10) ** 6 / Decimal(1000)
    if price <= 0:
        raise RuntimeError("Could not price LCAI.")
    return (target / price).quantize(Decimal("0.000000000000000001"))


def bridge_fees(amount_units: int) -> tuple[int, int]:
    recipient = bytes.fromhex(RECIPIENT[2:])
    data = "0x8bd90b82" + encode(["uint32", "bytes32", "uint256"], [DESTINATION, recipient, amount_units]).hex()
    raw = rpc("eth_call", [{"to": ROUTER, "data": data}, "latest"])
    quotes = decode(["(address,uint256)[]"], bytes.fromhex(raw[2:]))[0]
    native_fee = 0
    lcai_quoted = 0
    for token, fee in quotes:
        if int(token, 16) == 0:
            native_fee += fee
        elif token.lower() == LCAI.lower():
            lcai_quoted += fee
    token_fee = max(lcai_quoted - amount_units, 0)
    return native_fee, token_fee


def build(amount: Decimal, unit: str, entered: Decimal, contingency: Decimal) -> tuple[str, Path]:
    units = int((amount * Decimal(10) ** 18).to_integral_value(ROUND_DOWN))
    if units <= 0:
        raise RuntimeError("Amount must be greater than 0.")
    native_fee, token_fee = bridge_fees(units)
    approval = units + token_fee
    text = "\n".join([
        "LCAI Ethereum Clearing house to 9200 Clearing house bridge",
        "",
        f"{unit} entered: {entered}",
        f"Contingency % added: {contingency}",
        f"LCAI the 9200 safe should receive: {amount}",
        f"Bridge amount integer: {units}",
        f"Token fee integer: {token_fee}",
        f"Approval amount integer: {approval}",
        f"ETH value: {native_fee}",
        "",
        "Sender",
        f"Source: {ETH_SAFE}, Clearing house safe on Ethereum",
        f"LCAI: {LCAI}",
        f"Ethereum router: {ROUTER}",
        f"Destination domain: {DESTINATION}",
        "",
        "Recipient",
        f"9200 Clearing house safe: {DEST_SAFE}",
        f"_recipient: {RECIPIENT}",
        "",
        "Create transaction batch",
        f"Open ETH Clearing House Safe: {SAFE_URL}",
        "The network should show Ethereum, not 9200.",
        "New transaction, Transaction Builder. Two calls, one batch.",
        "",
        "Transaction 1 of 2: Approve",
        PASTE,
        f"Enter Address or ENS Name: {LCAI}",
        PROXY_NOTE,
        f"ABI: {APPROVE_ABI}",
        "Method: approve",
        "ETH value: 0",
        f"spender: {ROUTER}",
        f"amount: {approval}",
        "",
        "Transaction 2 of 2: transferRemote",
        PASTE,
        f"Enter Address or ENS Name: {ROUTER}",
        f"ABI: {TRANSFER_ABI}",
        "Method: transferRemote",
        f"_destination: {DESTINATION}",
        "If Safe reports a BigInt error on destination, clear the box and type 0x23f0.",
        f"_recipient: {RECIPIENT}",
        f"_amount: {units}",
        f"ETH value: {native_fee}",
        "",
        "Send",
        "1. Create batch.",
        "2. Simulate.",
        f"3. Open the Tenderly link on the simulation and confirm the safe LCAI balance drops by the approval amount {approval / 10**18} and no unexpected ETH leaves the safe.",
        "4. Send batch.",
        f"5. On the Confirm transaction screen, confirm the LCAI amount being bridged is {amount} before signing.",
        "6. Hit continue.",
        "7. Sign. Open Transactions, then Queue.",
        "8. Each signer opens the same Ethereum Clearing house safe, Queue, confirms the bridge amount, then Confirm.",
        "9. After the required signatures, any owner clicks Execute. Execution runs the approval and the bridge together.",
        "",
    ])
    amount_text = format(amount.quantize(Decimal("0.01")), "f")
    entered_text = format(entered.quantize(Decimal("0.01")), "f")
    filename = Path(f"{unit}-{entered_text}-bridge-{amount_text}-LCAI-ETH-to-9200.txt")
    filename.write_text(text)
    return text, filename


def ask_unit() -> str:
    while True:
        raw = input("Would you like to enter the amount to bridge in 1. $USD or 2. LCAI? ").strip().upper()
        if raw in {"1", "USD", "$USD"}:
            return "USD"
        if raw in {"2", "LCAI"}:
            return "LCAI"
        print("Enter 1 for $USD or 2 for LCAI.")


def ask_usd() -> Decimal:
    while True:
        raw = input("Enter in $USD the amount of LCAI you would like to bridge: ").strip().replace(",", "").replace("$", "")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            print("Enter a USD amount, for example 10.")
            continue
        if amount <= 0:
            print("Enter an amount greater than 0.")
            continue
        return amount


def ask_lcai() -> Decimal:
    while True:
        raw = input("How much LCAI would you like to bridge? ").strip().replace(",", "")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            print("Enter a decimal amount, for example 1000.")
            continue
        if amount <= 0:
            print("Enter an amount greater than 0.")
            continue
        return amount


def ask_contingency() -> Decimal:
    while True:
        raw = input("Contingency % to add for later fees (default 0%) [enter number between 0 and 15] ").strip().replace("%", "")
        if raw == "":
            return Decimal("0")
        try:
            contingency = Decimal(raw)
        except InvalidOperation:
            print("Enter a number from 0 to 15, or press Enter for 0%.")
            continue
        if contingency < Decimal("0") or contingency > Decimal("15"):
            print("Enter a number from 0 to 15, or press Enter for 0%.")
            continue
        return contingency


def main() -> None:
    unit = ask_unit()
    entered = ask_usd() if unit == "USD" else ask_lcai()
    contingency = ask_contingency()
    base = lcai_for_usd(entered) if unit == "USD" else entered
    if unit == "USD":
        print(f"Live quote for {entered} USD is about {base} LCAI.")
    amount = (base * (Decimal(100) + contingency) / Decimal(100)).quantize(Decimal("0.000000000000000001"))
    print(f"LCAI to bridge after {contingency}% contingency: {amount}")
    text, filename = build(amount, unit, entered, contingency)
    print()
    print(text)
    print(f"Saved: {filename.resolve()}")


if __name__ == "__main__":
    main()
