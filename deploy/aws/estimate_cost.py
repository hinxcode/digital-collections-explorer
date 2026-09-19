"""
Look up current AWS prices for one Digital Collections Explorer deployment.

Prices come from the AWS Price List API at the time of the call, so the estimate
shown before deploying is never a stale number copied into a script.
"""

import argparse
import json
import sys

import boto3

# The Price List API is only served from a few regions, whatever region is priced.
PRICING_API_REGION = "us-east-1"

# AWS bills by the hour and uses 730 hours as the length of a month.
HOURS_PER_MONTH = 730


def first_price(client, service_code, filters):
    """Return the first on-demand USD price matching the filters, or None"""
    response = client.get_products(
        ServiceCode=service_code,
        Filters=[
            {"Type": "TERM_MATCH", "Field": field, "Value": value}
            for field, value in filters.items()
        ],
        MaxResults=10,
    )
    for raw in response["PriceList"]:
        product = json.loads(raw)
        for term in product.get("terms", {}).get("OnDemand", {}).values():
            for dimension in term["priceDimensions"].values():
                price = float(dimension["pricePerUnit"]["USD"])
                if price > 0:
                    return price
    return None


def lookup(region, instance_type, disk_gib):
    """Return the monthly cost of each part, with None where no price was found"""
    client = boto3.client("pricing", region_name=PRICING_API_REGION)
    instance_hour = first_price(
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
    disk_gib_month = first_price(
        client,
        "AmazonEC2",
        {"regionCode": region, "productFamily": "Storage", "volumeApiName": "gp3"},
    )
    address_hour = first_price(
        client,
        "AmazonVPC",
        {"regionCode": region, "group": "VPCPublicIPv4Address"},
    )
    return {
        "machine": instance_hour and instance_hour * HOURS_PER_MONTH,
        "machine_hour": instance_hour,
        "disk": disk_gib_month and disk_gib_month * disk_gib,
        "address": address_hour and address_hour * HOURS_PER_MONTH,
    }


def render(costs, instance_type, disk_gib, region):
    """Format the estimate for a person to read before agreeing to it"""

    def money(value):
        return f"${value:,.2f}" if value is not None else "price not found"

    lines = [
        f"  Machine ({instance_type}, running all month)   {money(costs['machine'])}",
        f"  Disk ({disk_gib} GB)                            {money(costs['disk'])}",
        f"  Fixed public address                       {money(costs['address'])}",
    ]
    known = [costs[part] for part in ("machine", "disk", "address")]
    if all(value is not None for value in known):
        lines.append(
            f"  Total per month                            {money(sum(known))}"
        )
    else:
        lines.append("  Total: incomplete, because a price could not be found.")
    lines.append(
        f"  Current on-demand prices in {region}, from the AWS Price List API."
    )
    lines.append(
        "  Data sent out to visitors is billed separately and is usually small."
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--instance-type", required=True)
    parser.add_argument("--disk-gib", type=int, required=True)
    args = parser.parse_args()
    try:
        costs = lookup(args.region, args.instance_type, args.disk_gib)
    except Exception as error:
        print(f"  Prices could not be looked up ({type(error).__name__}).")
        print("  See https://aws.amazon.com/ec2/pricing/on-demand/ before continuing.")
        return 1
    print(render(costs, args.instance_type, args.disk_gib, args.region))
    return 0


if __name__ == "__main__":
    sys.exit(main())
