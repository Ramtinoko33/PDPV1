"""Per-flow handler registry."""
from . import pre_ticket, renting, mech_alert, assistencias

REGISTRY = {
    "pre_ticket": pre_ticket,
    "renting": renting,
    "mech_alert": mech_alert,
    "assistencias": assistencias,
}
