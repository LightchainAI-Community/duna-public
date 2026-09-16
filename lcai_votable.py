#!/usr/bin/env python3
"""
LCAI votable supply checker

What it does
  Reads Lightchain mainnet balances and prints:
    still in Hyperlane (not converted)
    released onto mainnet wallets
    treasury / deployer / burn (not votable)
    eligible voting power

How to run
  python3 lcai_votable.py
  python3 lcai_votable.py --block 1880038

Needs: Python 3. No pip packages.
"""

from __future__ import annotations

import argparse
import json
import urllib.request

RPC = "https://rpc.mainnet.lightchain.ai"

HYP = "0xEc7096A3116EE769457C939617375Ec1785AA6f1"
TREASURY = "0x786eDe8C42Ca54E54c9dCECa9b30052CF4743389"
DEPLOYER = "0xfbE810101064E326f871bf20576d8e42C75d5Dd7"
BURN = "0x000000000000000000000000000000000000dEaD"
NATIVE_VOTES = "0x0000000000000000000000000000000000001001"

# Fallback if the precompile call is unavailable.
# This is the getTotalVotingPower figure the DAO has been using.
DEFAULT_TVP = 9_964_600_000.0


def rpc(method: str, params):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(
        RPC, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]


def wei_to_lcai(hex_wei: str) -> float:
    return int(hex_wei, 16) / 10**18


def balance(addr: str, block: str) -> float:
    return wei_to_lcai(rpc("eth_getBalance", [addr, block]))


def try_total_voting_power(block: str) -> float | None:
    # getTotalVotingPower() selector 0x11acc1a7 (keccak of the signature)
    for data in ("0x11acc1a7", "0x2a1c1e70"):
        try:
            raw = rpc("eth_call", [{"to": NATIVE_VOTES, "data": data}, block])
            if raw and raw != "0x":
                return wei_to_lcai(raw)
        except Exception:
            continue
    return None


def fmt(n: float) -> str:
    return f"{n:,.2f}"


def main() -> None:
    p = argparse.ArgumentParser(description="LCAI eligible voting power")
    p.add_argument(
        "--block",
        default="latest",
        help="hex or decimal block number, or 'latest'",
    )
    args = p.parse_args()

    block = args.block
    if block != "latest" and not str(block).startswith("0x"):
        block = hex(int(block))

    head = int(rpc("eth_blockNumber", []), 16)
    used = head if args.block == "latest" else int(block, 16)

    hyp = balance(HYP, block)
    treasury = balance(TREASURY, block)
    deployer = balance(DEPLOYER, block)
    burn = balance(BURN, block)

    tvp = try_total_voting_power(block)
    tvp_note = "on-chain getTotalVotingPower"
    if tvp is None:
        tvp = DEFAULT_TVP
        tvp_note = "fallback constant (precompile call failed)"

    released = tvp - hyp
    votable = released - treasury - deployer - burn

    print("LCAI votable supply")
    print(f"RPC            {RPC}")
    print(f"Block          {used} ({block})")
    print()
    print(f"Native voting power     {fmt(tvp)}    ({tvp_note})")
    print(f"Still in Hyperlane      {fmt(hyp)}")
    print(f"  {HYP}")
    print(f"Released to wallets     {fmt(released)}")
    print()
    print(f"Treasury (not votable)  {fmt(treasury)}")
    print(f"  {TREASURY}")
    print(f"Deployer (not votable)  {fmt(deployer)}")
    print(f"  {DEPLOYER}")
    print(f"Burn (not votable)      {fmt(burn)}")
    print(f"  {BURN}")
    print()
    print(f"Eligible voting power   {fmt(votable)}")
    print(f"Majority (50% + dust)   {fmt(votable / 2)}")
    print()
    print("Eligible = released minus treasury, deployer, and burn.")
    print("Released = native voting power minus Hyperlane balance.")
    print("Use --block <snapshot> for a live proposal.")


if __name__ == "__main__":
    main()
