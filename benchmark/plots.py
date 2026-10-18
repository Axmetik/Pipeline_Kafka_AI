"""Static, exportable figures; windows fixed by the preregistered protocol."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from benchmark.models import MODEL_ORDER


def save_plots(predictions, overall, timing, config, output):
    output.mkdir(parents=True, exist_ok=True)
    times = pd.to_datetime(predictions.forecast_target_timestamp)

    def save(fig, name):
        fig.tight_layout()
        for extension in ('png', 'svg'):
            fig.savefig(output / f'{name}.{extension}', dpi=160)
        plt.close(fig)

    mask = times < times.iloc[0] + pd.Timedelta(days=config['overview_days'])
    fig, axes = plt.subplots(4, 1, figsize=(14, 11), sharex=True)
    for ax, name in zip(axes, MODEL_ORDER):
        ax.plot(times[mask], predictions.loc[mask, 'actual_energy_wh'], color='black', label='Actual', linewidth=1)
        ax.plot(times[mask], predictions.loc[mask, name], label=name, alpha=.75, linewidth=.8)
        ax.set_ylabel('Wh / 10 min'); ax.legend(loc='upper right')
    fig.suptitle('First seven test days: one-step forecasts')
    save(fig, 'forecast_overview')

    chosen = []
    for index in predictions.actual_energy_wh.sort_values(ascending=False, kind='stable').index:
        time = times.loc[index]
        if all(abs(time - other) >= pd.Timedelta(hours=2 * config['peak_window_hours']) for other in chosen):
            chosen.append(time)
        if len(chosen) == config['peak_episodes']:
            break
    fig, axes = plt.subplots(len(chosen), 1, figsize=(14, 3.5 * len(chosen)), squeeze=False)
    for ax, center in zip(axes[:, 0], chosen):
        mask = abs(times - center) <= pd.Timedelta(hours=config['peak_window_hours'])
        ax.plot(times[mask], predictions.loc[mask, 'actual_energy_wh'], color='black', label='Actual', linewidth=2)
        for name in MODEL_ORDER:
            ax.plot(times[mask], predictions.loc[mask, name], label=name, alpha=.8)
        ax.set_title(f'High-load episode around {center}'); ax.set_ylabel('Wh / 10 min'); ax.legend()
    save(fig, 'peak_episodes')

    errors = [predictions[name] - predictions.actual_energy_wh for name in MODEL_ORDER]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for name, error in zip(MODEL_ORDER, errors):
        axes[0].hist(error, bins=80, histtype='step', label=name)
    axes[0].set_yscale('log'); axes[0].set_xlabel('Prediction − actual (Wh)'); axes[0].set_ylabel('Count (log scale)'); axes[0].legend()
    axes[1].boxplot(errors, tick_labels=MODEL_ORDER); axes[1].tick_params(axis='x', rotation=25); axes[1].set_ylabel('Prediction − actual (Wh)')
    save(fig, 'errors')
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, metric in zip(axes[:2], ('mae_wh', 'rmse_wh')):
        ax.bar(MODEL_ORDER, [overall[n][metric] for n in MODEL_ORDER]); ax.set_ylabel(metric)
    axes[2].bar(MODEL_ORDER, [timing[n]['median_us'] for n in MODEL_ORDER]); axes[2].set_yscale('log'); axes[2].set_ylabel('Median single-row inference (µs, log)')
    for ax in axes:
        ax.tick_params(axis='x', rotation=35)
    save(fig, 'comparison')
