# Portfolio risk methodology — v0.2

## Data provenance

- **Live public spot quotes:** Kraken Spot REST. No API credentials.
- **Completed 1d candles:** Kraken Spot OHLC endpoint (`interval=1440`), no unfinished candle.
- **Portfolio quantity, cost basis, venue:** Hypothetical local JSON, never real holdings.
- **Cross-venue marks:** All assets use Kraken prices even if the venue label says otherwise.

## Deterministic risk scenarios

For each current asset exposure \(V_i\) and shock \(s_i\) in percent:

\[ \Delta V = \sum_i V_i \frac{s_i}{100} \]

These are instant parallel mark changes. No trading, liquidity, basis, fee, collateral,
or order-book effects. The static-price shock is *not* a forecast.

## Concentration

Weights are current asset-value fractions \(w_i\). HHI = \(\sum w_i^2\),
and effective asset count = \(1 / HHI\). This is concentration only;
it does not capture return correlation, tail risk or downside dependence.

## Historical returns and risk

At each completed common UTC daily close, infer a synthetic portfolio value
\(P_t = \sum_i q_i p_{it}\) using **present fictional quantities** \(q_i\).
Daily simple returns: \(r_t=P_t/P_{t-1}-1\). This is an illustrative
retrospective fixed-quantity portfolio, **not** a verified live trading history,
not rebalanced, and not a strategy backtest.

- Historical daily VaR at 95% = max(0, -5th empirical percentile of returns).
- Expected Shortfall = max(0, negative average of returns at/below the VaR quantile).
- Annualized historical volatility = sample std(daily returns) × sqrt(365).
- Max drawdown = min(\(P_t/\max_{s\le t}P_s-1\)).
- Correlation = sample Pearson correlation of synchronized daily asset returns.

USD VaR and ES apply historical percent estimates to **today's marked portfolio**.
Confidence is statistical, not certainty. Up to 720 historical Kraken OHLC records
are available per interval. Current v0.2 accepts 60–365 days and returns an
explicit unavailable error for insufficient or missing date histories.

## Known limitations

No fees, slippage, deposits, withdrawals, market impact, real-time execution,
short exposure, margin/leverage, funding, futures, options, taxes, exchange-specific
prices, wallet balances, asset transfers, trade ledger or realized P&L. The
latest trade price is not guaranteed to be executable at that price.

For demo/education only. Not financial advice.
