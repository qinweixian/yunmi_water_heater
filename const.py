"""Constants for the Yunmi (云米) water heater integration."""

from homeassistant.const import Platform

DOMAIN = "yunmi"

PLATFORMS = [
    Platform.WATER_HEATER,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
]

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_NAME = "热水器"

# One-shot preheat: one button + duration per water outlet (floor)
ONE_SHOT_SLOTS = ("floor1", "floor2")
DEFAULT_ONE_SHOT_DURATIONS = {"floor1": 45, "floor2": 55}
MIN_ONE_SHOT_DURATION = 10
MAX_ONE_SHOT_DURATION = 3600

MIN_TEMP = 30
MAX_TEMP = 65

MIIO_PORT = 54321

# viomi.waterheater.* LAN miio protocol
GET_PROPS = [
    "washStatus",
    "velocity",
    "waterTemp",
    "targetTemp",
    "errStatus",
    "isPreHeatNow",
    "preHeatTime1",
    "preHeatTime2",
    "preHeatTime3",
]

# Extra props used by some Viomi heaters (e.g. e1); probed once, optional
EXTENDED_PROPS = ["hotWater", "needClean", "modeType", "appointStart", "appointEnd"]

# targetTemp doubles as mode indicator: 30-65 = custom temperature,
# these codes = preset wash modes (set via set_temp)
WASH_MODE_CODES = {
    39: "儿童洗",
    40: "舒适洗",
    42: "老人洗",
    36: "厨房用",
}

# washStatus semantics (miot spec: 0 off / 1 idle / 2 busy / 3 preheat)
WASH_STATUS_LABELS = {
    0: "关机",
    1: "待机",
    2: "加热中",
    3: "预热中",
}
