"""Reorder planning maths shared by the Inventory and What-If pages."""
from statistics import NormalDist
import numpy as np


def plan_reorder(inv, lead, service, horizon=3, demand_mult=1.0, sigma_mult=1.0):
    """Safety stock = z x monthly std x sqrt(lead); reorder point = demand over lead time + safety stock.
    demand_mult / sigma_mult let the What-If page stress the inputs."""
    z = NormalDist().inv_cdf(service)
    p = inv.copy()
    p['mu'] = p[f'fc_qty_next{horizon}'] / horizon * demand_mult
    p['safety'] = np.ceil(z * p['std_monthly_qty'] * sigma_mult * np.sqrt(lead))
    p['rop'] = np.ceil(p['mu'] * lead + p['safety'])
    return p
