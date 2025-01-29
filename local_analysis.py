from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import time
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# Set up the SQLAlchemy session (adjust the database URL accordingly)
engine = create_engine("sqlite:///test.db")
Session = sessionmaker(bind=engine)
session = Session()

# Import models from your module (adjust the import path if necessary)
from core.models import Matchmaking, Elo, Game, PlayerGame

# Define the time window (last 30 days)
thirty_days_ago = time.time() - (30 * 24 * 60 * 60)

###############################################
# 1. Retrieve Data for Matchmaking & Elo
###############################################

# Query for matchmaking records joined with the current Elo values
mm_query = session.query(
    Matchmaking.id,
    Matchmaking.environment_id,
    Matchmaking.model_name,
    Elo.elo,
    Matchmaking.joined_at
).join(
    Elo,
    (Matchmaking.model_name == Elo.model_name) &
    (Matchmaking.environment_id == Elo.environment_id)
).filter(
    Matchmaking.joined_at >= thirty_days_ago
)
matchmaking_data = mm_query.all()

# Query for game-player data joined with their Elo values in the selected time window.
# We use Game.started_at as the game timestamp.
game_query = session.query(
    Game.id.label("game_id"),
    PlayerGame.model_name,
    Elo.elo,
    Game.started_at
).join(
    PlayerGame, Game.id == PlayerGame.game_id
).join(
    Elo,
    (PlayerGame.model_name == Elo.model_name) &
    (Game.environment_id == Elo.environment_id)
).filter(
    Game.started_at >= thirty_days_ago
)
game_player_data = game_query.all()

# Create dataframes for further analysis
df_matchmaking = pd.DataFrame(matchmaking_data, columns=["matchmaking_id", "environment_id", "model_name", "elo", "joined_at"])
df_game = pd.DataFrame(game_player_data, columns=["game_id", "model_name", "elo", "started_at"])

###############################################
# 2. Compute Game-level Elo Statistics
###############################################

# Group by game_id and compute metrics for each game.
# Note: We assume that for a given game, started_at is the same for all participants.
game_elo_stats = df_game.groupby("game_id").agg(
    max_elo=("elo", "max"),
    min_elo=("elo", "min"),
    mean_elo=("elo", "mean"),
    std_elo=("elo", "std"),
    count_players=("elo", "count"),
    game_started_at=("started_at", "min")  # Taking the earliest timestamp per game.
).reset_index()

# Calculate Elo difference
game_elo_stats["elo_diff"] = game_elo_stats["max_elo"] - game_elo_stats["min_elo"]

print(game_elo_stats.head())
print("Average Elo difference:", game_elo_stats["elo_diff"].mean())
print("Median Elo difference:", game_elo_stats["elo_diff"].median())

###############################################
# 3. Visualization: Elo Difference Distribution
###############################################

# Plot distribution of Elo differences per game
sns.histplot(game_elo_stats["elo_diff"], kde=True)
plt.title("Distribution of Elo Differences per Game")
plt.xlabel("Elo Difference")
plt.ylabel("Frequency")
plt.show()

# Plot distribution of Elo standard deviations per game
sns.histplot(game_elo_stats["std_elo"].dropna(), kde=True)
plt.title("Distribution of Elo Standard Deviation per Game")
plt.xlabel("Elo Standard Deviation")
plt.ylabel("Frequency")
plt.show()

###############################################
# 4. Analysis: Model Appearance Counts
###############################################

# Count the number of appearances per model in player games
model_counts = df_game["model_name"].value_counts()
print("Top Models by Appearance:")
print(model_counts.head())

# Plot the top 10 models by game appearances
model_counts.head(10).plot(kind="bar")
plt.title("Top 10 Models by Game Appearance")
plt.xlabel("Model Name")
plt.ylabel("Number of Appearances")
plt.show()

###############################################
# 5. Analysis: Elo Difference by Environment
###############################################

# If you have a column that references a specific environment id in player games,
# adjust the code below accordingly. If not, you can use environment_id from the matchmaking data.
# For demonstration, let’s assume `specific_env_id` is available; if not, replace it with "environment_id".
if "specific_env_id" in df_game.columns:
    merge_key = "specific_env_id"
else:
    merge_key = "environment_id"

# To merge, we first need to bring the environment id into game_elo_stats if available.
# Here we assume game-level data has the appropriate environment identifier.
# For simplicity, we'll merge on game_id and then group by environment if that information exists.
# If environment_id is not present in df_game, you can analyze directly by game.
# For the purpose of this example, we proceed as if we have environment_id.
# (If not, comment out the merge and grouping section.)

# For this example, we simulate that df_game has an "environment_id" column.
if "environment_id" in df_game.columns:
    env_elo_diff = df_game.drop_duplicates(subset=["game_id"]).merge(
        game_elo_stats[["game_id", "elo_diff"]],
        on="game_id"
    )
    
    env_stats = env_elo_diff.groupby("environment_id").agg(
        avg_elo_diff=("elo_diff", "mean"),
        game_count=("game_id", "nunique")
    ).reset_index()

    print("Elo Diff by Environment:")
    print(env_stats)

    sns.barplot(x="environment_id", y="avg_elo_diff", data=env_stats)
    plt.title("Average Elo Difference per Environment")
    plt.xlabel("Environment ID")
    plt.ylabel("Average Elo Difference")
    plt.show()

###############################################
# 6. Additional Analysis: Elo Difference Over Time
###############################################

# Option 1: Scatter plot of Elo difference vs game start time.
plt.figure(figsize=(10, 6))
plt.scatter(game_elo_stats["game_started_at"], game_elo_stats["elo_diff"], alpha=0.6)
plt.title("Elo Difference per Game Over Time")
plt.xlabel("Game Start Time (timestamp)")
plt.ylabel("Elo Difference")
plt.show()

# Option 2: Aggregate by day to see daily average Elo differences.
# Convert timestamp to a datetime object and then to date.
game_elo_stats["game_date"] = pd.to_datetime(game_elo_stats["game_started_at"], unit='s').dt.date
daily_stats = game_elo_stats.groupby("game_date").agg(
    avg_daily_elo_diff=("elo_diff", "mean"),
    game_count=("game_id", "count")
).reset_index()

plt.figure(figsize=(12, 6))
sns.lineplot(data=daily_stats, x="game_date", y="avg_daily_elo_diff", marker="o")
plt.title("Daily Average Elo Difference")
plt.xlabel("Date")
plt.ylabel("Average Elo Difference")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

###############################################
# 7. Frequency Analysis: Matches with Elo Difference Thresholds
###############################################

# Count matches where elo_diff <= 100 and > 100.
low_diff_count = (game_elo_stats["elo_diff"] <= 100).sum()
high_diff_count = (game_elo_stats["elo_diff"] > 100).sum()

print(f"Number of games with Elo difference <= 100: {low_diff_count}")
print(f"Number of games with Elo difference > 100: {high_diff_count}")

# Create a DataFrame for visualization.
diff_categories = pd.DataFrame({
    "Elo Difference Category": ["<= 100", "> 100"],
    "Count": [low_diff_count, high_diff_count]
})

sns.barplot(x="Elo Difference Category", y="Count", data=diff_categories)
plt.title("Frequency of Elo Difference Categories")
plt.xlabel("Elo Difference Category")
plt.ylabel("Number of Games")
plt.show()
