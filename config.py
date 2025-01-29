DATABASE_URL = "sqlite:///./test.db"
DEFAULT_ELO = 1000
MIN_GAMES_LEADERBOARD = 1

# K-factor settings
HUMAN_K_FACTOR = 8
STANDARD_MODEL_K_FACTOR = 8
INITIAL_K = 32
REDUCED_K = 16
GAMES_THRESHOLD = 50

# Timeouts
MATCHMAKING_INACTIVITY_TIMEOUT = 30
STEP_TIMEOUT = 180 #60

# Matchmaking
MATCHMAKING_INTERVAL = 3
MAX_ELO_DELTA = 400
PCT_TIME_BASE = 0.5
NUM_RECENT_GAMES_CAP = 25
MIN_WAIT_FOR_STANDARD = 60

RATE_LIMIT = 100_000

# Standard model names
STANDARD_MODELS = [] #"google/gemini-flash-1.5"]
HUMANITY_MODEL_NAME = "Humanity"

# Environment related
DEFAULT_ENV_ID = "BalancedSubset-v0"
ENV_NAME_TO_ID = {
  'TruthAndDeception-v0': '0',
  'DontSayIt-v0': '1',
  'Poker-v0': '2',
  'SpellingBee-v0': '3',
  'Tak-v0': '4',
  'Chess-v0': '5',
  'LiarsDice-v0': '6',
  'UltimateTicTacToe-v0': '7',
  'Stratego-v0': '8',
  'Negotiation-v0': '9',
  'unknown': '10'
}