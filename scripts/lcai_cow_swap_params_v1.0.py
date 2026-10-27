#!/usr/bin/env python3
"""Size an LCAI sell for CoW Swap so the worst fill still covers a USD target.

Outputs the field values needed to set the order in the Ethereum Clearing House Safe.
CoW handles the actual transaction building.
"""

import json
import urllib.request
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pathlib import Path

LCAI = "0x9cA8530CA349c966Fe9ef903Df17a75B8A778927"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
RPCS = ["https://eth.drpc.org", "https://rpc.mevblocker.io", "https://ethereum-rpc.publicnode.com"]
TOKENS = {
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
}
SAFE = "0xba69032451D2682b413d18422cef40781af32755"


def path_for(stable: str) -> bytes:
    return (
        bytes.fromhex(LCAI[2:])
        + (3000).to_bytes(3, "big")
        + bytes.fromhex(WETH[2:])
        + (500).to_bytes(3, "big")
        + bytes.fromhex(TOKENS[stable][2:])
    )


def quote(route: bytes, amount: int) -> int:
    from eth_abi import encode, decode
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


def lcai_for_usd(target: Decimal, stable: str) -> Decimal:
    quoted = quote(path_for(stable), 1000 * 10**18)
    price = Decimal(quoted) / Decimal(10) ** 6 / Decimal(1000)
    if price <= 0:
        raise RuntimeError("Could not price LCAI.")
    return (target / price).quantize(Decimal("0.000000000000000001"))


def recommended_slippage(amount: Decimal, stable: str) -> Decimal:
    units = int((amount * Decimal(10) ** 18).to_integral_value(ROUND_DOWN))
    small = quote(path_for(stable), 1000 * 10**18)
    large = quote(path_for(stable), units)
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
    return recommended


def cover_target(target: Decimal, stable: str, slippage: Decimal) -> tuple[Decimal, Decimal, int]:
    amount = lcai_for_usd(target, stable)
    keep = (Decimal(100) - slippage) / Decimal(100)
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


def ask_usd() -> Decimal:
    while True:
        raw = input("Enter in $USD the amount of LCAI ERC-20 you would like to convert: ").strip().replace(",", "").replace("$", "")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            print("Enter a USD amount, for example 10000.")
            continue
        if amount <= 0:
            print("Enter an amount greater than 0.")
            continue
        return amount


def ask_stable() -> str:
    while True:
        raw = input("What would you like to swap it for 1. USDC or 2. USDT? ").strip().upper()
        if raw in {"1", "USDC"}:
            return "USDC"
        if raw in {"2", "USDT"}:
            return "USDT"
        print("Enter 1 for USDC or 2 for USDT.")


def ask_slippage(default: Decimal) -> Decimal:
    while True:
        raw = input(f"Max slippage % (recommended {default}%) [0.5-10, Enter to accept]: ").strip().replace("%", "")
        if raw == "":
            return default
        try:
            slippage = Decimal(raw)
        except InvalidOperation:
            print("Enter a number from 0.5 to 10, or press Enter.")
            continue
        if slippage < Decimal("0.5") or slippage > Decimal("10"):
            print("Enter a number from 0.5 to 10, or press Enter.")
            continue
        return slippage


def main() -> None:
    target = ask_usd()
    stable = ask_stable()
    seed = lcai_for_usd(target, stable)
    default_slippage = recommended_slippage(seed, stable)
    print(f"\nLive Uniswap quote implies ~{seed} LCAI for ${target}.")
    print(f"Recommended slippage for this size: {default_slippage}%")
    slippage = ask_slippage(default_slippage)

    amount, quoted, min_out = cover_target(target, stable, slippage)
    received = Decimal(min_out) / Decimal(10) ** 6
    units = int((amount * Decimal(10) ** 18).to_integral_value(ROUND_DOWN))

    print("\n" + "=" * 60)
    print("CoW Swap order parameters for Ethereum Clearing House Safe")
    print("=" * 60)
    print(f"Safe:                 {SAFE}")
    print(f"Sell token:           LCAI ERC-20")
    print(f"Sell token address:   {LCAI}")
    print(f"Sell amount:          {amount}")
    print(f"Sell amount (raw):    {units}")
    print(f"Buy token:            {stable}")
    print(f"Buy token address:    {TOKENS[stable]}")
    print(f"Slippage tolerance:   {slippage}%")
    print(f"Minimum {stable} out:  {received}")
    print(f"Minimum raw (6 dec):  {min_out}")
    print(f"Quoted (before slip): {quoted} {stable}")
    print("=" * 60)
    print("\nEnter these values in CoW Swap (Safe app or explorer).")
    print("CoW will build and present the signing/execution flow.")
    print(f"Worst case at {slippage}% slippage still delivers at least {received} {stable}.")

    text = "\n".join([
        "CoW Swap order parameters for Ethereum Clearing House Safe",
        "",
        f"Safe:                 {SAFE}",
        f"Sell token:           LCAI ERC-20",
        f"Sell token address:   {LCAI}",
        f"Sell amount:          {amount}",
        f"Sell amount (raw):    {units}",
        f"Buy token:            {stable}",
        f"Buy token address:    {TOKENS[stable]}",
        f"Slippage tolerance:   {slippage}%",
        f"Minimum {stable} out:  {received}",
        f"Minimum raw (6 dec):  {min_out}",
        f"Quoted (before slip): {quoted} {stable}",
        "",
        f"Worst case at {slippage}% slippage still delivers at least {received} {stable}.",
    ])
    lcai_fmt = format(amount.quantize(Decimal("0.01")), "f")
    usd_fmt = format(target.quantize(Decimal("0.01")), "f")
    filename = Path(__file__).parent / f"USD-{usd_fmt}-sell-{lcai_fmt}-LCAI-ERC20-to-{stable}.txt"
    filename.write_text(text)
    print(f"\nSaved: {filename.resolve()}")


if __name__ == "__main__":
    main()
