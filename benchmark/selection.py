"""Selection has no test-data argument. Frozen choices precede final evaluation."""
from sklearn.model_selection import ParameterGrid
from benchmark.models import MODEL_ORDER, make_model, predict
from benchmark.features import BENCHMARK_FEATURES
from benchmark.evaluation import error_metrics


def tune_on_validation(train, validation, protocol):
    xtrain = train[BENCHMARK_FEATURES].to_numpy(dtype=float)
    xval = validation[BENCHMARK_FEATURES].to_numpy(dtype=float)
    ytrain, yval = train.actual_energy_wh.to_numpy(), validation.actual_energy_wh.to_numpy()
    trials, selected, scores = [], {}, {}
    for name in MODEL_ORDER:
        if name in ('persistence', 'seasonal_naive'):
            scores[name] = error_metrics(yval, predict(make_model(name), xval))
            selected[name] = {}
            continue
        grid_name = 'rf_grid' if name == 'random_forest' else 'hgb_grid'
        candidates = []
        for candidate, params in enumerate(ParameterGrid(protocol[grid_name])):
            model = make_model(name, params, protocol['seed'])
            model.fit(xtrain, ytrain)
            score = error_metrics(yval, predict(model, xval))
            row = {'model': name, 'candidate': candidate, 'parameters': params, **score}
            trials.append(row)
            candidates.append(row)
            print(f"Validation {name} candidate={candidate}: MAE={score['mae_wh']:.6f}", flush=True)
        best = min(candidates, key=lambda r: (r['mae_wh'], r['rmse_wh'], r['candidate']))
        selected[name] = best['parameters']
        scores[name] = {key: best[key] for key in error_metrics(yval, yval)}
    winner = min(MODEL_ORDER, key=lambda name: (scores[name]['mae_wh'], scores[name]['rmse_wh'], MODEL_ORDER.index(name)))
    return {'parameters': selected, 'validation_metrics': scores,
            'recommended_by_validation': winner, 'selection_uses_test': False}, trials


def refit_selected(train_validation, selection, seed):
    x = train_validation[BENCHMARK_FEATURES].to_numpy(dtype=float)
    y = train_validation.actual_energy_wh.to_numpy()
    models = {}
    for name in MODEL_ORDER:
        model = make_model(name, selection['parameters'][name], seed)
        if name not in ('persistence', 'seasonal_naive'):
            model.fit(x, y)
        models[name] = model
    return models
