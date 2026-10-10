#!/usr/bin/env python3
"""v1.1: bridge enough LCAI for the later swap script, including its slippage and 0.25% buffer, then add contingency."""

import json
import urllib.request
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pathlib import Path

from eth_abi import encode, decode

SOURCE_SAFE = "0xFc21263493BD8EBD99C8E4A9Fc249A5087A6e047"
ETH_SAFE = "0xba69032451D2682b413d18422cef40781af32755"
ROUTER = "0xEc7096A3116EE769457C939617375Ec1785AA6f1"
DESTINATION = 1
RECIPIENT = "0x000000000000000000000000ba69032451D2682b413d18422cef40781af32755"
LCAI = "0x9cA8530CA349c966Fe9ef903Df17a75B8A778927"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
TOKENS = {
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
}
QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
RPCS = ["https://eth.drpc.org", "https://rpc.mevblocker.io", "https://ethereum-rpc.publicnode.com"]
SAFE_URL = f"https://safe.lightchain.ai/transactions/history?safe=lcai:{SOURCE_SAFE}"
ABI = '[{"inputs":[{"name":"_destination","type":"uint32"},{"name":"_recipient","type":"bytes32"},{"name":"_amount","type":"uint256"}],"name":"transferRemote","outputs":[{"name":"messageId","type":"bytes32"}],"stateMutability":"payable","type":"function"}]'
PASTE = "Copy and paste values into the transaction builder fields exactly as shown. Replace any ABI data present with what is provided if applicable."


def path_for(stable: str) -> bytes:
    return (
        bytes.fromhex(LCAI[2:])
        + (3000).to_bytes(3, "big")
        + bytes.fromhex(WETH[2:])
        + (500).to_bytes(3, "big")
        + bytes.fromhex(TOKENS[stable][2:])
    )


def quote(route: bytes, amount: int) -> int:
    data = "0xcdca1753" + encode(["bytes", "uint256"], [route, amount]).hex()
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": QUOTER, "data": data}, "latest"]}).encode()
    for url in RPCS:
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "lcai"})
            result = json.loads(urllib.request.urlopen(req, timeout=20).read())["result"]
            amount_out = decode(["uint256"], bytes.fromhex(result[2:66]))[0]
            if amount_out > 0:
                return amount_out
        except Exception:
            continue
    raise RuntimeError("Could not price LCAI. Check the network connection and run again.")


def lcai_for_usd(target: Decimal, stable: str) -> Decimal:
    quoted = quote(path_for(stable), 1000 * 10**18)
    price = Decimal(quoted) / Decimal(10) ** 6 / Decimal(1000)
    if price <= 0:
        raise RuntimeError("Could not price LCAI.")
    return (target / price).quantize(Decimal("0.000000000000000001"))


def recommended_slippage(amount: Decimal, stable: str) -> tuple[Decimal, Decimal]:
    units = int((amount * Decimal(10) ** 18).to_integral_value(ROUND_DOWN))
    small = quote(path_for(stable), 1000 * 10**18)
    large = quote(path_for(stable), units)
    quoted = Decimal(large) / Decimal(10) ** 6
    small_px = Decimal(small) / Decimal(1000)
    large_px = Decimal(large) / amount
    impact = max((small_px - large_px) / small_px * Decimal(100), Decimal(0))
    raw = impact + Decimal(1)
    steps = (raw * 2).to_integral_value(rounding="ROUND_CEILING")
    recommended = steps / Decimal(2)
    if recommended < Decimal("1"):
        recommended = Decimal("1")
    if recommended > Decimal("10"):
        recommended = Decimal("10")
    return recommended, quoted


def ask_slippage(default: Decimal) -> Decimal:
    while True:
        raw = input(f"Later swap max slippage % (default {default}%) [enter number between 0.5 and 10%] ").strip().replace("%", "")
        if raw == "":
            return default
        try:
            slippage = Decimal(raw)
        except InvalidOperation:
            print("Enter a number from 0.5 to 10, or press Enter for the default.")
            continue
        if slippage < Decimal("0.5") or slippage > Decimal("10"):
            print("Enter a number from 0.5 to 10, or press Enter for the default.")
            continue
        return slippage


def cover_target(target: Decimal, stable: str, slippage: Decimal) -> tuple[Decimal, Decimal, int]:
    amount = lcai_for_usd(target, stable)
    keep = (Decimal(100) - slippage) / Decimal(100)
    quoted = Decimal(0)
    min_out = 1
    for _ in range(6):
        units = int((amount * Decimal(10) ** 18).to_integral_value(ROUND_DOWN))
        quoted_raw = quote(path_for(stable), units)
        quoted = Decimal(quoted_raw) / Decimal(10) ** 6
        min_out = max(int(Decimal(quoted_raw) * keep), 1)
        received = Decimal(min_out) / Decimal(10) ** 6
        covered = target * Decimal("1.0025")
        if received >= covered:
            return amount, quoted, min_out
        amount = (amount * covered / received * Decimal("1.0025")).quantize(Decimal("0.000000000000000001"))
    return amount, quoted, min_out


def ask_stable() -> str:
    while True:
        raw = input("What will the later swap convert it to 1. USDC or 2. USDT? ").strip().upper()
        if raw in {"1", "USDC"}:
            return "USDC"
        if raw in {"2", "USDT"}:
            return "USDT"
        print("Enter 1 for USDC or 2 for USDT.")


def build(amount: Decimal, unit: str, entered: Decimal, contingency: Decimal, slippage: Decimal) -> tuple[str, Path]:
    units = int((amount * Decimal(10) ** 18).to_integral_value(ROUND_DOWN))
    if units <= 0:
        raise RuntimeError("Amount must be greater than 0.")
    text = "\n".join([
        "LCAI 9200 to Ethereum Clearing house bridge",
        "",
        f"{unit} entered: {entered}",
        f"Later swap slippage %: {slippage}",
        "Later swap buffer: 0.25%",
        f"Contingency % added: {contingency}",
        f"LCAI to bridge: {amount}",
        f"Bridge amount integer: {units}",
        f"Transaction value integer: {units}",
        "",
        "Sender",
        f"Source: {SOURCE_SAFE}, Clearing house safe on chain ID 9200",
        f"9200 router: {ROUTER}",
        f"Destination domain: {DESTINATION}",
        "Approval: None. This router is the native wrapper.",
        "",
        "Recipient",
        f"Ethereum Safe: {ETH_SAFE}",
        f"_recipient: {RECIPIENT}",
        "",
        "Create transaction batch",
        f"Open 9200 Clearing house Safe: {SAFE_URL}",
        "The network should show 9200, not Ethereum.",
        "New transaction, Transaction Builder. One call. Do not add a second call.",
        "",
        "Transaction 1 of 1: transferRemote",
        PASTE,
        f"Enter Address or ENS Name: {ROUTER}",
        f"ABI: {ABI}",
        "Method: transferRemote",
        f"_destination: {DESTINATION}",
        f"_recipient: {RECIPIENT}",
        f"_amount: {units}",
        f"LCAI value (decimal): {amount}",
        "",
        "Send",
        "1. Create batch. Do not add a second contract call.",
        "2. Send batch.",
        f"3. On the Confirm transaction screen, confirm the LCAI amount being bridged is {amount} before signing.",
        "4. Hit continue.",
        "5. Sign. Open Transactions, then Queue.",
        "6. Each signer opens the same 9200 safe, Queue, confirms the bridge amount, then Confirm.",
        "7. After the required signatures, any owner clicks Execute. Execution sends the native LCAI and the bridge message together.",
        "8. Transaction fees are paid by the final signer from their wallet. Ask for reimbursement if needed.",
        "",
    ])
    amount_text = format(amount.quantize(Decimal("0.01")), "f")
    entered_text = format(entered.quantize(Decimal("0.01")), "f")
    filename = Path(f"{unit}-{entered_text}-bridge-{amount_text}-LCAI-9200-to-ETH.txt")
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
            print("Enter a USD amount, for example 14500.")
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
            print("Enter a decimal amount, for example 16000000.")
            continue
        if amount <= 0:
            print("Enter an amount greater than 0.")
            continue
        return amount


def ask_contingency() -> Decimal:
    while True:
        raw = input("Contingency % to add for later fees (default 5%) [enter number between 1 and 15] ").strip().replace("%", "")
        if raw == "":
            return Decimal("5")
        try:
            contingency = Decimal(raw)
        except InvalidOperation:
            print("Enter a number from 1 to 15, or press Enter for 5%.")
            continue
        if contingency < Decimal("1") or contingency > Decimal("15"):
            print("Enter a number from 1 to 15, or press Enter for 5%.")
            continue
        return contingency


def main() -> None:
    unit = ask_unit()
    entered = ask_usd() if unit == "USD" else ask_lcai()
    stable = ask_stable()
    contingency = ask_contingency()
    slippage = Decimal("0")
    if unit == "USD":
        seed = lcai_for_usd(entered, stable)
        default_slippage, quoted = recommended_slippage(seed, stable)
        print(f"Live quote for {entered} USD is about {seed} LCAI, quoting {quoted} {stable}.")
        print(f"Recommended later-swap slippage for this size: {default_slippage}%")
        slippage = ask_slippage(default_slippage)
        base, quoted, min_out = cover_target(entered, stable, slippage)
        received = Decimal(min_out) / Decimal(10) ** 6
        print(f"The later swap script will sell {base} LCAI to cover {entered} {stable} after {slippage}% slippage and a 0.25% buffer.")
        print(f"That sell quotes {quoted} {stable}. Worst case is {received} {stable}.")
    else:
        base = entered
    amount = (base * (Decimal(100) + contingency) / Decimal(100)).quantize(Decimal("0.000000000000000001"))
    print(f"LCAI to bridge after {contingency}% contingency: {amount}")
    text, filename = build(amount, unit, entered, contingency, slippage)
    print()
    print(text)
    print(f"Saved: {filename.resolve()}")


if __name__ == "__main__":
    main()
