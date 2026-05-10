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
            nn.Linear(input_dim, 8),
            nn.ReLU(),
            nn.Linear(8, 2)
        )

        self.decoder = nn.Sequential(
            nn.Linear(2, 8),
            nn.ReLU(),
            nn.Linear(8, input_dim)
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded


class AutoencoderAnomalyDetector:
    def __init__(self, window_size: int = 100, threshold_percentile: int = 95):
        self.window_size = window_size
        self.threshold_percentile = threshold_percentile

        self.buffer: List[List[float]] = []
        self.recent_window = deque(maxlen=window_size)

        self.scaler = StandardScaler()
        self.model = Autoencoder(input_dim=4)
        self.loss_fn = nn.MSELoss()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.01)

        self.is_trained = False
        self.threshold = None

    def _extract_features(self, data: Dict[str, Any]) -> List[float]:
        return [
            float(data["temperature"]),
            float(data["humidity"]),
            float(data["light"]),
            float(data["voltage"])
        ]

    def train(self, data_window: List[List[float]], epochs: int = 50) -> None:
        scaled_data = self.scaler.fit_transform(np.array(data_window))
        train_tensor = torch.tensor(scaled_data, dtype=torch.float32)

        self.model.train()

        for _ in range(epochs):
            reconstructed = self.model(train_tensor)
            loss = self.loss_fn(reconstructed, train_tensor)

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

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

    def detect(self, data: Dict[str, Any]) -> Dict[str, Any]:
        features = self._extract_features(data)

        self.buffer.append(features)
        self.recent_window.append(features)

        if not self.is_trained:
            if len(self.buffer) >= self.window_size:
                self.train(self.buffer)

            data["autoencoder_anomaly"] = False
            data["autoencoder_reconstruction_error"] = 0.0
            return data

        scaled = self.scaler.transform(np.array([features]))
        input_tensor = torch.tensor(scaled, dtype=torch.float32)

        self.model.eval()

        with torch.no_grad():
            reconstructed = self.model(input_tensor)
            reconstruction_error = torch.mean(
                (input_tensor - reconstructed) ** 2
            ).item()

        data["autoencoder_reconstruction_error"] = round(reconstruction_error, 6)
        data["autoencoder_anomaly"] = reconstruction_error > self.threshold

        return data