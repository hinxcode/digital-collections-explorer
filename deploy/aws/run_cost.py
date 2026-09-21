"""Price an indexing run and the machine that is serving now, from the machine's own report."""

import argparse
import json
import sys
from datetime import datetime, timezone

import boto3
from estimate_cost import HOURS_PER_MONTH, PRICING_API_REGION, first_price

# The machine type that is enough for serving searches.
SERVING_MACHINE = "t3.medium"
WORTH_MENTIONING_USD_PER_MONTH = 5


def machine_hour_price(client, region, instance_type):
    """Return the on-demand hourly USD price of one machine type, or None"""
    if not instance_type:
        return None
    return first_price(
        client,
        "AmazonEC2",
        {
            "regionCode": region,
            "instanceType": instance_type,
            "operatingSystem": "Linux",
            "tenancy": "Shared",
            "preInstalledSw": "NA",
            "capacitystatus": "Used",
        },
    )


def hours_since(moment, now=None):
    """Hours between an ISO timestamp and now"""
    now = now or datetime.now(timezone.utc)
    then = datetime.strptime(moment, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (now - then).total_seconds() / 3600


def cost_lines(report, current_type, indexed_on, price_of, now=None):
    """Describe what indexing cost and what the running machine costs"""
    run = report["run"]
    lines = []
    indexing_type = indexed_on or run.get("machine_type")
    indexing_price = price_of(indexing_type)
    hours = run["active_seconds"] / 3600

    if indexing_price is not None and hours:
        cost = hours * indexing_price
        lines.append(
            f"Indexing cost about ${cost:,.2f} "
            f"({hours:.1f} hours on {indexing_type} at ${indexing_price:.4f} per hour)"
        )
        if report["indexed"]:
            per_thousand = cost / report["indexed"] * 1000
            lines.append(f"  That is ${per_thousand:.3f} per 1,000 images")
    elif hours:
        lines.append(
            "The machine type used for indexing was not recorded, so it cannot be "
            "priced. Pass --indexed-on TYPE to price it."
        )

    current_price = price_of(current_type)
    if current_price is not None:
        monthly = current_price * HOURS_PER_MONTH
        lines.append(
            f"Running now: {current_type} at ${current_price:.4f} per hour, "
            f"about ${monthly:,.2f} per month while it stays on"
        )
        serving_price = price_of(SERVING_MACHINE)
        saving = (current_price - (serving_price or 0)) * HOURS_PER_MONTH
        is_finished = bool(run.get("finished_at"))
        if is_finished and serving_price and saving > WORTH_MENTIONING_USD_PER_MONTH:
            idle = hours_since(run["finished_at"], now)
            lines.append(
                f"WARNING: indexing finished {idle:.0f} hours ago and this machine is "
                f"larger than serving needs. Switching to {SERVING_MACHINE} saves about "
                f"${saving:,.2f} per month. Run deploy.sh again with "
                f"--instance-type {SERVING_MACHINE}; the index is kept."
            )
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--current-type", required=True)
    parser.add_argument("--indexed-on")
    args = parser.parse_args()
    report = json.load(sys.stdin)
    client = boto3.client("pricing", region_name=PRICING_API_REGION)
    prices = {}

    def price_of(instance_type):
        if instance_type not in prices:
            try:
                prices[instance_type] = machine_hour_price(
                    client, args.region, instance_type
                )
            except Exception:
                prices[instance_type] = None
        return prices[instance_type]

    for line in cost_lines(report, args.current_type, args.indexed_on, price_of):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
