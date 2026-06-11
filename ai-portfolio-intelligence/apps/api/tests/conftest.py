import os

# Force broker mode to default ibkr_readonly for test suite configuration isolation,
# ensuring developer overrides in local .env do not fail base configuration tests.
os.environ["BROKER_MODE"] = "ibkr_readonly"
