"""Fixed CPU autoencoder, shared by training and inference."""
import numpy as np
import torch
from torch import nn
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline


def preprocessing():
    return Pipeline([('imputer', SimpleImputer(strategy='median', keep_empty_features=True)),
                     ('scaler', StandardScaler())])


def network(hidden):
    widths = [20, *hidden, *list(reversed(hidden[:-1])), 20]
    layers = []
    for i, (a, b) in enumerate(zip(widths, widths[1:])):
        layers.append(nn.Linear(a, b))
        if i < len(widths) - 2:
            layers.append(nn.ReLU())
    return nn.Sequential(*layers)


def fit_ae(x, config, seed):
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    split = int(len(x) * (1 - config['early_stop_fraction']))
    if split < 2 or split == len(x):
        raise ValueError('Insufficient AE train/early-stop samples')
    prep = preprocessing().fit(x[:split])
    fit = torch.tensor(prep.transform(x[:split]), dtype=torch.float32)
    hold = torch.tensor(prep.transform(x[split:]), dtype=torch.float32)

    def initialize():
        torch.manual_seed(seed)
        model = network(config['hidden'])
        optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])
        return model, optimizer

    def epoch(model, optimizer, data):
        model.train()
        for start in range(0, len(data), config['batch_size']):
            batch = data[start:start + config['batch_size']]
            optimizer.zero_grad()
            loss = ((model(batch) - batch) ** 2).mean()
            loss.backward(); optimizer.step()

    model, optimizer = initialize()
    best, best_epoch, stale = float('inf'), 0, 0
    history = []
    for count in range(1, config['max_epochs'] + 1):
        epoch(model, optimizer, fit)
        model.eval()
        with torch.no_grad():
            loss = float(((model(hold) - hold) ** 2).mean())
        history.append(loss)
        if loss < best:
            best, best_epoch, stale = loss, count, 0
        else:
            stale += 1
        if stale >= config['patience']:
            break
    prep = preprocessing().fit(x)
    data = torch.tensor(prep.transform(x), dtype=torch.float32)
    model, optimizer = initialize()
    for _ in range(best_epoch):
        epoch(model, optimizer, data)
    model.eval()
    return prep, model, {'epochs': best_epoch, 'early_stop_losses': history, 'internal_fit_count': split}


def ae_score(prep, model, x):
    model.eval()
    with torch.no_grad():
        values = torch.tensor(prep.transform(x), dtype=torch.float32)
        return ((model(values) - values) ** 2).mean(dim=1).numpy().astype(float)
