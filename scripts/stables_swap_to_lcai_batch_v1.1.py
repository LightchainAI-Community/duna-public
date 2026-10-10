#!/usr/bin/env python3
"""v1.1: swap USDC or USDT to LCAI. Size the spend so a LCAI target still clears after slippage."""

import json
import time
import urllib.request
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pathlib import Path

from eth_abi import encode, decode

SAFE = "0xba69032451D2682b413d18422cef40781af32755"
LCAI = "0x9cA8530CA349c966Fe9ef903Df17a75B8A778927"
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
ROUTER = "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
RPCS = ["https://eth.drpc.org", "https://rpc.mevblocker.io", "https://ethereum-rpc.publicnode.com"]
TOKENS = {
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
}
PASTE = "Copy and paste values into the transaction builder fields exactly as shown. Replace any ABI data present with what is provided if applicable. If Safe offers a proxy implementation ABI, decline it and keep the address shown."
APPROVE_ABI = '[{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]'
PERMIT2_ABI = '[{"inputs":[{"name":"token","type":"address"},{"name":"spender","type":"address"},{"name":"amount","type":"uint160"},{"name":"expiration","type":"uint48"}],"name":"approve","outputs":[],"stateMutability":"nonpayable","type":"function"}]'
EXECUTE_ABI = '[{"inputs":[{"name":"commands","type":"bytes"},{"name":"inputs","type":"bytes[]"},{"name":"deadline","type":"uint256"}],"name":"execute","outputs":[],"stateMutability":"payable","type":"function"}]'


def path_for(stable: str) -> bytes:
    return (
        bytes.fromhex(TOKENS[stable][2:])
        + (500).to_bytes(3, "big")
        + bytes.fromhex(WETH[2:])
        + (3000).to_bytes(3, "big")
        + bytes.fromhex(LCAI[2:])
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
    raise RuntimeError("Could not quote the swap. Check the network connection and run again.")


def build(spend: Decimal, stable: str, slippage: Decimal, unit: str, entered: Decimal) -> tuple[str, Path]:
    units = int((spend * Decimal(10) ** 6).to_integral_value(ROUND_DOWN))
    if units <= 0:
        raise RuntimeError("Amount must be greater than 0.")
    route = path_for(stable)
    quoted_raw = quote(route, units)
    quoted = Decimal(quoted_raw) / Decimal(10) ** 18
    keep = (Decimal(100) - slippage) / Decimal(100)
    min_out = max(int(Decimal(quoted_raw) * keep), 1)
    deadline = int(time.time()) + 48 * 60 * 60
    pull = encode(["address", "address", "uint160"], [TOKENS[stable], "0x0000000000000000000000000000000000000002", units]).hex()
    swap = encode(["address", "uint256", "uint256", "bytes", "bool"], ["0x0000000000000000000000000000000000000001", units, min_out, route, False]).hex()
    calls = []
    if stable == "USDT":
        calls.extend([
            "Transaction 1 of 4: Reset USDT approval",
            PASTE,
            f"Enter Address or ENS Name: {TOKENS[stable]}",
            "Transaction Builder may prompt you to use the proxy ABI or the implementation ABI. Choose proxy ABI, which keeps the address you pasted. Then replace the ABI the tool provides with the ABI below.",
            f"ABI: {APPROVE_ABI}",
            "Method: approve",
            "ETH value: 0",
            f"spender: {PERMIT2}",
            "amount: 0",
            "",
        ])
        approve_n, permit_n, execute_n, total = 2, 3, 4, 4
    else:
        approve_n, permit_n, execute_n, total = 1, 2, 3, 3
    calls.extend([
        f"Transaction {approve_n} of {total}: Approve",
        PASTE,
        f"Enter Address or ENS Name: {TOKENS[stable]}",
        "Transaction Builder may prompt you to use the proxy ABI or the implementation ABI. Choose proxy ABI, which keeps the address you pasted. Then replace the ABI the tool provides with the ABI below.",
        f"ABI: {APPROVE_ABI}",
        "Method: approve",
        "ETH value: 0",
        f"spender: {PERMIT2}",
        f"amount: {units}",
        "",
        f"Transaction {permit_n} of {total}: Permit2 approve",
        PASTE,
        f"Enter Address or ENS Name: {PERMIT2}",
        f"ABI: {PERMIT2_ABI}",
        "Method: approve",
        "ETH value: 0",
        f"token: {TOKENS[stable]}",
        f"spender: {ROUTER}",
        f"amount: {units}",
        f"expiration: {deadline}",
        "",
        f"Transaction {execute_n} of {total}: Execute",
        PASTE,
        f"Enter Address or ENS Name: {ROUTER}",
        f"ABI: {EXECUTE_ABI}",
        "Method: execute",
        "ETH value: 0",
        "commands: 0x0200",
        f'inputs: ["0x{pull}","0x{swap}"]',
        f"deadline: {deadline}",
    ])
    text = "\n".join([
        f"{stable} to LCAI execution",
        "",
        f"{unit} entered: {entered}",
        f"{stable} to spend: {spend}",
        f"Spend amount integer: {units}",
        f"Quoted LCAI: {quoted}",
        f"Max slippage %: {slippage}",
        f"Minimum LCAI out, raw 18-decimal units: {min_out}",
        f"Expiration and deadline: {deadline}",
        "",
        "Create transaction batch",
        f"Open ETH Clearing House Safe: https://app.safe.global/home?safe=eth:{SAFE}",
        "New transaction, Transaction Builder. ETH value 0 on every call.",
        "",
        *calls,
        "",
        "Send",
        "1. Create batch.",
        "2. Simulate.",
        f"3. Open the Tenderly link on the simulation and confirm the safe {stable} balance drops by {spend} and LCAI arrives at the same safe. No ETH leaves the safe.",
        "4. Send batch.",
        f"5. On the Confirm transaction screen, confirm the {stable} amount being swapped is {spend} before signing.",
        "6. Hit continue.",
        "7. Sign. Open Transactions, then Queue.",
        "8. Each signer opens the same safe, Queue, confirms the spend amount, then Confirm.",
        "9. After the required signatures, any owner clicks Execute.",
        "",
    ])
    spend_text = format(spend.quantize(Decimal("0.01")), "f")
    entered_text = format(entered.quantize(Decimal("0.01")), "f")
    filename = Path(f"{unit}-{entered_text}-spend-{spend_text}-{stable}-to-LCAI.txt")
    filename.write_text(text)
    return text, filename


def ask_unit() -> str:
    while True:
        raw = input("Would you like to enter the amount to convert in 1. $USD or 2. LCAI erc-20? ").strip().upper()
        if raw in {"1", "USD", "$USD"}:
            return "USD"
        if raw in {"2", "LCAI", "LCAI ERC-20"}:
            return "LCAI"
        print("Enter 1 for $USD or 2 for LCAI erc-20.")


def ask_usd() -> Decimal:
    while True:
        raw = input("Enter in $USD the amount of stablecoin you would like to convert: ").strip().replace(",", "").replace("$", "")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            print("Enter a USD amount, for example 100.")
            continue
        if amount <= 0:
            print("Enter an amount greater than 0.")
            continue
        return amount


def ask_lcai() -> Decimal:
    while True:
        raw = input("How much LCAI erc-20 would you like to receive? ").strip().replace(",", "")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            print("Enter a decimal amount, for example 1000 or 5.001.")
            continue
        if amount <= 0:
            print("Enter an amount greater than 0.")
            continue
        return amount


def ask_stable() -> str:
    while True:
        raw = input("What stablecoin would you like to swap from 1. USDC or 2. USDT? ").strip().upper()
        if raw in {"1", "USDC"}:
            return "USDC"
        if raw in {"2", "USDT"}:
            return "USDT"
        print("Enter 1 for USDC or 2 for USDT.")


def stable_for_lcai(target: Decimal, stable: str) -> Decimal:
    quoted = quote(path_for(stable), 1000 * 10**6)
    lcai_out = Decimal(quoted) / Decimal(10) ** 18
    if lcai_out <= 0:
        raise RuntimeError("Could not price the stablecoin.")
    return (target / lcai_out * Decimal(1000)).quantize(Decimal("0.000001"))


def recommended_slippage(spend: Decimal, stable: str) -> tuple[Decimal, Decimal]:
    units = int((spend * Decimal(10) ** 6).to_integral_value(ROUND_DOWN))
    small = quote(path_for(stable), 1000 * 10**6)
    large = quote(path_for(stable), units)
    quoted = Decimal(large) / Decimal(10) ** 18
    small_px = Decimal(small) / Decimal(1000)
    large_px = Decimal(large) / spend
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
        raw = input(f"max slippage % (default {default}%) [enter number between 0.5 and 10%] ").strip().replace("%", "")
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
    spend = stable_for_lcai(target, stable)
    keep = (Decimal(100) - slippage) / Decimal(100)
    quoted = Decimal(0)
    min_out = 1
    for _ in range(6):
        units = int((spend * Decimal(10) ** 6).to_integral_value(ROUND_DOWN))
        quoted_raw = quote(path_for(stable), units)
        quoted = Decimal(quoted_raw) / Decimal(10) ** 18
        min_out = max(int(Decimal(quoted_raw) * keep), 1)
        received = Decimal(min_out) / Decimal(10) ** 18
        covered = target * Decimal("1.0025")
        if received >= covered:
            return spend, quoted, min_out
        spend = (spend * covered / received * Decimal("1.0025")).quantize(Decimal("0.000001"))
    return spend, quoted, min_out


def ask_cover(target: Decimal, stable: str, slippage: Decimal) -> Decimal:
    spend, quoted, min_out = cover_target(target, stable, slippage)
    received = Decimal(min_out) / Decimal(10) ** 18
    print(f"To receive at least {target} LCAI after {slippage}% slippage, plus a 0.25% buffer, spend {spend} {stable}.")
    print(f"That spend quotes {quoted} LCAI. Worst case at this slippage is {received} LCAI.")
    while True:
        raw = input(f"Press Enter to spend that amount, or enter a larger {stable} amount: ").strip().replace(",", "")
        if raw == "":
            return spend
        try:
            chosen = Decimal(raw)
        except InvalidOperation:
            print(f"Enter a {stable} amount, or press Enter to accept the recommendation.")
            continue
        if chosen < spend:
            print(f"That is below the amount needed to cover {target} LCAI. Enter at least {spend}.")
            continue
        return chosen


def main() -> None:
    unit = ask_unit()
    if unit == "USD":
        entered = ask_usd()
    else:
        entered = ask_lcai()
    stable = ask_stable()
    if unit == "USD":
        spend = entered
        default_slippage, quoted = recommended_slippage(spend, stable)
        print(f"Live quote for spending {spend} {stable}: {quoted} LCAI")
    else:
        spend = stable_for_lcai(entered, stable)
        default_slippage, quoted = recommended_slippage(spend, stable)
        print(f"Live quote for {entered} LCAI is about {spend} {stable}, quoting {quoted} LCAI.")
    print(f"Recommended slippage for this size: {default_slippage}%")
    slippage = ask_slippage(default_slippage)
    if unit == "LCAI":
        spend = ask_cover(entered, stable, slippage)
    text, filename = build(spend, stable, slippage, unit, entered)
    print()
    print(text)
    print(f"Saved: {filename.resolve()}")


if __name__ == "__main__":
    main()
