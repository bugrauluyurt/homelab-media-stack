- An empty `NTFY_SERVER` in `.env` now falls back to ntfy.sh in the Python scripts too, as it
  already did in the bash ones, instead of sending alerts to an empty address.
