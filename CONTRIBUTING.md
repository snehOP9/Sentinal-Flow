# Contributing

Use Python 3.11+, run `make setup`, then `make test lint`. Keep new features
point-in-time safe: a transaction's features may only use events strictly earlier than
its event timestamp. Never commit secrets, production data, payment card details, or
model metrics that cannot be reproduced from the committed synthetic generator.
