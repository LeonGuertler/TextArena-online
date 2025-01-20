# TextArena Matchmaking & Elo System


TODO
- fix queue dropout issue (again)







This setup provides:
- Model registration
- Matchmaking
- Ongoing game management
- Elo rating updates after each game
- Statistics logging to Weights & Biases (W&B)

## How to Run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt






- queue all requests
- make sure they are executed sequentially?


- activity table is not working


- route (hash) to thread based on model id


- change K over time (start at 32, decrease to 16 over the first 200 games. Then keep at 16 [should be game-wise])


- make sure you can't get matched to models submitted from the same IP address (to prevent abuse)

- limit how many models somebody can submit at the same time [like 10 at the same time]

-



- for the change in elo plot, remove connecting lines if the distance is too big

- serverside, for each game, push a nice render for the client side .render function


- client side, remove from game and matchmaking if you cancel


- value function for elo (maybe take recent matches into account)


- api request to check queue and active players for each game


- limit the leaderboard to only show people with enough games