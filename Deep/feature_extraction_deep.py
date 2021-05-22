import sktime
from sktime.transformations.panel.rocket import MiniRocket
import pandas as pd
from torchvision.models import resnet18
import os
import numpy as np
import torch
from pyts.image import GramianAngularField, MarkovTransitionField, RecurrencePlot
from typing import List




def time_series_to_features(time_series_lst: List[np.ndarray]) -> List[np.ndarray]:
    mini = MiniRocket(num_features=1000)
    time_series_lst = time_series_lst.reshape(time_series_lst.shape[0], 1, time_series_lst.shape[1])
    transformed = mini.fit_transform(time_series_lst).values
    return transformed

# We would use GAF  - Gramian Angular Fields, which are images represent time series in non carterian mode
# Instead of using x, y as images, where each x y is determined using refernce point, angle


def time_series_to_images(time_series_lst: List[np.ndarray], vers: str = 'gramian') -> List[np.ndarray]:
    mrk = MarkovTransitionField()
    rp = RecurrencePlot()
    gasf = GramianAngularField(image_size=24, method='summation')
    imgs = rp.fit_transform(time_series_lst)
    return imgs


def load_pretrained_model(model_name: str):
    if model_name == 'resnet18':
        resnet = resnet18(pretrained=True)
        removed = list(resnet.children())[:-1]
        model = torch.nn.Sequential(*removed)
        return model


model = load_pretrained_model(model_name='resnet18')
model = model.float()


def images_to_feature_vector(lst_imgs):
    lst_imgs = np.stack((lst_imgs, lst_imgs, lst_imgs), axis=1)
    tensor_data = torch.tensor(lst_imgs)
    res = model(tensor_data.float())
    res = torch.squeeze(res)
    # print(res.shape)
    return res