READ_ONLY_BROKER_ACTIONS = {
    "get_accounts",
    "get_account_summary",
    "get_positions",
    "get_transactions",
    "get_open_orders_readonly",
    "get_latest_price",
    "health_check",
}

FORBIDDEN_BROKER_ACTIONS = {
    "place_order",
    "modify_order",
    "cancel_order",
    "execute_trade",
    "rebalance",
    "submit_order",
}


def assert_readonly_action(action: str) -> None:
    if action in FORBIDDEN_BROKER_ACTIONS or action not in READ_ONLY_BROKER_ACTIONS:
        raise PermissionError(f"Broker action {action!r} is not allowed in this read-only system.")
