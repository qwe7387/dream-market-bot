from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def create_price_timeline(
    item_name: str,
    records: list[dict[str, Any]],
) -> BytesIO:
    """Create a PNG timeline for observed listing and economy prices."""

    valid_records: list[dict[str, Any]] = []

    for record in records:
        try:
            checked_at = _parse_timestamp(str(record["checked_at"]))
            listing_price = int(record["listing_price"])
            net_after_tax = int(record["net_after_tax"])
            average_price = int(record["average_price"])
        except (KeyError, TypeError, ValueError):
            continue

        valid_records.append(
            {
                "checked_at": checked_at,
                "listing_price": listing_price,
                "net_after_tax": net_after_tax,
                "average_price": average_price,
            }
        )

    if not valid_records:
        raise ValueError("No valid history records were available for a graph.")

    times = [record["checked_at"] for record in valid_records]
    listing_prices = [record["listing_price"] for record in valid_records]
    net_prices = [record["net_after_tax"] for record in valid_records]
    average_prices = [record["average_price"] for record in valid_records]

    figure, axis = plt.subplots(figsize=(10, 5.5))

    axis.plot(
        times,
        listing_prices,
        marker="o",
        linewidth=2,
        label="Current FM listing",
    )
    axis.plot(
        times,
        net_prices,
        marker="o",
        linewidth=2,
        label="Net after tax",
    )
    axis.plot(
        times,
        average_prices,
        linestyle="--",
        linewidth=2,
        label="7-day economy average",
    )

    axis.set_title(f"Observed price timeline — {item_name}")
    axis.set_xlabel("Check time")
    axis.set_ylabel("Mesos")
    axis.grid(True, alpha=0.25)
    axis.legend()

    locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axis.ticklabel_format(axis="y", style="plain")

    figure.autofmt_xdate()
    figure.tight_layout()

    output = BytesIO()
    figure.savefig(output, format="png", dpi=150, bbox_inches="tight")
    plt.close(figure)

    output.seek(0)
    return output
