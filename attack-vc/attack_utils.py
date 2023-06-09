import torch
import torch.nn as nn
from torch import Tensor
from tqdm import trange
import generate_masking_threshold as generate_mask
import numpy as np


class Transform(object):
    '''
    Return: PSD
    '''
    def __init__(self, window_size):
        self.scale = 8. / 3.
        self.frame_length = int(window_size)
        self.frame_step = int(window_size // 4)
        self.window_size = window_size

    def __call__(self, x, psd_max_ori):
        win = torch.stft(x, self.frame_length, self.frame_step)
        z = self.scale * torch.abs(win / self.window_size)
        psd = torch.square(z)
        PSD = torch.pow(10., 9.6) / psd_max_ori.view(-1, 1, 1) * psd

        return PSD


def psychoacoustic_loss(adv_audio, original, psd_max_a, th,transform):
    logits_delta = transform((adv_audio[0, :] - original[0, :]), psd_max_a[0])
    psychoacoustic_loss = torch.mean(torch.nn.functional.relu(logits_delta - th[0]))
    return psychoacoustic_loss



def emb_attack_psy(
    model: nn.Module, vc_tgt: Tensor, adv_tgt: Tensor, eps: float, n_iters: int
) -> Tensor:
    ptb = torch.zeros_like(vc_tgt).normal_(0, 1).requires_grad_(True)
    opt = torch.optim.Adam([ptb])
    criterion = nn.MSELoss()
    pbar = trange(n_iters)


    with torch.no_grad():
        org_emb = model.speaker_encoder(vc_tgt)
        tgt_emb = model.speaker_encoder(adv_tgt)

    th, psd_max = generate_mask.generate_th(org_emb.float, 16000, 2048)
    th = np.expand_dims(th, 0)
    psd_max = np.expand_dims(psd_max, 0)
    transform = Transform(2048)
    psd_max_a = torch.tensor(psd_max, dtype=torch.float32)
    psy = psychoacoustic_loss(adv_tgt, vc_tgt, psd_max_a, th, transform)

    for _ in pbar:
        adv_inp = vc_tgt + eps * ptb.tanh()
        adv_emb = model.speaker_encoder(adv_inp)
        loss = criterion(adv_emb, tgt_emb) - 0.1 * psy
        opt.zero_grad()
        loss.backward()
        opt.step()

    return vc_tgt + eps * ptb.tanh()


def emb_attack(
    model: nn.Module, vc_tgt: Tensor, adv_tgt: Tensor, eps: float, n_iters: int
) -> Tensor:
    ptb = torch.zeros_like(vc_tgt).normal_(0, 1).requires_grad_(True)
    opt = torch.optim.Adam([ptb])
    criterion = nn.MSELoss()
    pbar = trange(n_iters)

    with torch.no_grad():
        org_emb = model.speaker_encoder(vc_tgt)
        tgt_emb = model.speaker_encoder(adv_tgt)

    for _ in pbar:
        adv_inp = vc_tgt + eps * ptb.tanh()
        adv_emb = model.speaker_encoder(adv_inp)
        loss = criterion(adv_emb, tgt_emb) - 0.1 * criterion(adv_emb, org_emb)
        opt.zero_grad()
        loss.backward()
        opt.step()

    return vc_tgt + eps * ptb.tanh()


def fb_attack(
    model: nn.Module,
    vc_src: Tensor,
    vc_tgt: Tensor,
    adv_tgt: Tensor,
    eps: float,
    n_iters: int,
) -> Tensor:
    ptb = torch.zeros_like(vc_tgt).normal_(0, 1).requires_grad_(True)
    opt = torch.optim.Adam([ptb])
    criterion = nn.MSELoss()
    pbar = trange(n_iters)

    with torch.no_grad():
        org_emb = model.speaker_encoder(model.inference(vc_src, vc_tgt))
        tgt_emb = model.speaker_encoder(adv_tgt)

    for _ in pbar:
        adv_inp = vc_tgt + eps * ptb.tanh()
        adv_emb = model.speaker_encoder(model.inference(vc_src, adv_inp))
        loss = criterion(adv_emb, tgt_emb) - 0.1 * criterion(adv_emb, org_emb)
        opt.zero_grad()
        loss.backward()
        opt.step()

    return vc_tgt + eps * ptb.tanh()
