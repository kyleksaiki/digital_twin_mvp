"""TinyCNN architecture for binary audio detection.

VENDORED unmodified from the audio-detection repo (src/model/architecture.py).
To re-sync: copy the upstream file over this one and restore this header.
NOTE: this is NOT the legacy TinyCNN in audio_workflow/tiny_cnn_birdcall.py —
the classifier here starts with AdaptiveAvgPool2d((8, 16)) and ends at a raw
logit (no Sigmoid). Checkpoints are not interchangeable between the two.

The model takes a single-channel mel spectrogram and outputs one
probability (meaningful vs. not meaningful).

Input shape: (batch, 1, n_mels, time_frames) — any size.
AdaptiveAvgPool2d fixes the spatial dimensions to (8, 16) before
the classifier, so the model works regardless of spectrogram shape.
"""

import torch.nn as nn


class TinyCNN(nn.Module):
    def __init__(self):
        super(TinyCNN, self).__init__()
        self.conv_block1 = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.conv_block2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.conv_block3 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d((8, 16)),
            nn.Flatten(),
            nn.Linear(64 * 8 * 16, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 1),  # raw logit — apply sigmoid externally for inference
        )

    def forward(self, x):
        x = self.conv_block1(x)
        x = self.conv_block2(x)
        x = self.conv_block3(x)
        x = self.classifier(x)
        return x