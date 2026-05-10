from typing import Dict, Any, List
from collections import deque

import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler


class Autoencoder(nn.Module):
    def __init__(self, input_dim: int = 4):
        super().__init__()

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 4)
        )

        self.decoder = nn.Sequential(
            nn.Linear(4, 8),
            nn.ReLU(),
            nn.Linear(8, 16),
            nn.ReLU(),
            nn.Linear(16, input_dim)
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded


class AutoencoderAnomalyDetector:
    def __init__(
        self,
        window_size: int = 2000,
        retrain_interval: int = 2000,
        threshold_percentile: int = 99,
        epochs: int = 30,
        learning_rate: float = 0.001
    ):
        self.window_size = window_size
        self.retrain_interval = retrain_interval
        self.threshold_percentile = threshold_percentile
        self.epochs = epochs
        self.learning_rate = learning_rate

        self.recent_window = deque(maxlen=window_size)
        self.records_seen = 0

        self.scaler = StandardScaler()
        self.model = Autoencoder(input_dim=4)
        self.loss_fn = nn.MSELoss()
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.learning_rate
        )

        self.is_trained = False
        self.threshold = None
        self.last_training_loss = None

    def _extract_features(self, data: Dict[str, Any]) -> List[float]:
        return [
            float(data["temperature"]),
            float(data["humidity"]),
            float(data["light"]),
            float(data["voltage"])
        ]

    def _should_train(self) -> bool:
        if len(self.recent_window) < self.window_size:
            return False

        if not self.is_trained:
            return True

        return self.records_seen % self.retrain_interval == 0

    def train(self) -> None:
        train_data = np.array(self.recent_window)

        scaled_data = self.scaler.fit_transform(train_data)
        train_tensor = torch.tensor(scaled_data, dtype=torch.float32)

        self.model = Autoencoder(input_dim=4)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.learning_rate
        )

        self.model.train()

        last_loss = 0.0

        for _ in range(self.epochs):
            reconstructed = self.model(train_tensor)
            loss = self.loss_fn(reconstructed, train_tensor)

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

            last_loss = float(loss.item())

        self.last_training_loss = round(last_loss, 6)

        self.model.eval()

        with torch.no_grad():
            reconstructed = self.model(train_tensor)
            reconstruction_errors = torch.mean(
                (train_tensor - reconstructed) ** 2,
                dim=1
            ).numpy()

        self.threshold = float(
            np.percentile(reconstruction_errors, self.threshold_percentile)
        )

        self.is_trained = True

        print(
            f"Autoencoder retrained | "
            f"window={self.window_size} | "
            f"threshold={round(self.threshold, 6)} | "
            f"loss={self.last_training_loss}"
        )

    def detect(self, data: Dict[str, Any]) -> Dict[str, Any]:
        features = self._extract_features(data)

        self.records_seen += 1
        self.recent_window.append(features)

        if self._should_train():
            self.train()

        if not self.is_trained:
            data["autoencoder_anomaly"] = False
            data["autoencoder_reconstruction_error"] = 0.0
            data["autoencoder_threshold"] = 0.0
            data["autoencoder_training_loss"] = 0.0
            return data

        scaled = self.scaler.transform(np.array([features]))
        input_tensor = torch.tensor(scaled, dtype=torch.float32)

        self.model.eval()

        with torch.no_grad():
            reconstructed = self.model(input_tensor)
            reconstruction_error = torch.mean(
                (input_tensor - reconstructed) ** 2
            ).item()

        data["autoencoder_reconstruction_error"] = round(
            float(reconstruction_error),
            6
        )
        data["autoencoder_threshold"] = round(float(self.threshold), 6)
        data["autoencoder_training_loss"] = self.last_training_loss or 0.0
        data["autoencoder_anomaly"] = reconstruction_error > self.threshold

        return data