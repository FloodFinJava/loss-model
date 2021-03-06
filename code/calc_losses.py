# -*- coding: utf-8 -*-

"""Calculate losses maps and write them as GPKG
"""

import os
import sys
import csv

import json
import toml
import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


CONF_FILE = "conf.toml"

# Load configuration data from the toml file as a dict
with open(CONF_FILE, 'r') as toml_file:
    toml_string = toml_file.read()
conf = toml.loads(toml_string)
ASSETS_MAP_PATH = os.path.abspath(os.path.join(conf['input']['base_path'],
                                               conf['input']['assets']['map_name']))
LOSS_CURVES_DIR = conf['input']['loss_curves']['path']
LOSS_CURVES_EXTENSION = conf['input']['loss_curves']['extension']
LOSS_CURVE_RES = conf['input']['loss_curves']['index_resolution']
LOSS_CURVE_MAX = conf['input']['loss_curves']['max_index']
LOSS_CURVES_COL_NAMES = conf['input']['loss_curves']['col_names']


def load_loss_curves():
    """Load loss curves
    Resample them
    return a dict of pandas series
    """
    loss_curves = {}
    for f in os.listdir(LOSS_CURVES_DIR):
        basename, ext = os.path.splitext(f)
        if ext == LOSS_CURVES_EXTENSION:
            # Read curve
            full_path = os.path.abspath(os.path.join(LOSS_CURVES_DIR, f))
            loss_curve = pd.read_csv(full_path, squeeze=True, header=None,
                                     names=LOSS_CURVES_COL_NAMES, index_col=0)
            # Interpolate
            new_index = np.arange(LOSS_CURVE_MAX, step=LOSS_CURVE_RES)
            loss_curve1 = loss_curve.reindex(loss_curve.index.union(new_index))
            loss_curve1.interpolate('index', inplace=True)
            # convert to int at the given resolution
            loss_curve1.index = np.round(loss_curve1.index / LOSS_CURVE_RES)
            loss_curve1.index = loss_curve1.index.map(np.int32)
            # Remove duplicates
            loss_curve1 = loss_curve1[~loss_curve1.index.duplicated(keep='first')]
            # add to dict
            loss_curves[basename] = loss_curve1
    return loss_curves


def calculate_perc_loss(asset_row, depth_col, loss_curves):
    """take a geopandas row as entry
    Find the adequate loss curve
    return a percentage of loss
    """
    # If the curve is found
    curve_name = str(asset_row['loss_curve'])
    if curve_name in loss_curves.keys():
        loss_curve = loss_curves[curve_name]
        depth_cm = int(round(asset_row[depth_col] / LOSS_CURVE_RES))
        try:
            return loss_curve.at[depth_cm]
        except KeyError:
            print("Water depth {}({}) not found in loss curve {}".format(asset_row[depth_col], depth_cm, curve_name))
    else:
        print("Loss curve <{}> unknown".format(curve_name))


def apply_losses(asset_map, loss_curves):
    """For a given flood map and asset map:
    For each asset:
        find the adequate the losse curve,
        Get the % of loss from the flood map and loss curve,
        apply that % loss to the asset value
        Keep the asset loss in the geodataframe
    """
    asset_value_col = conf['input']['assets']['value']
    intensities = conf['input']['flood_map']['intensities']
    for intensity in intensities:
        intensity_col = intensity + conf['input']['assets']['intensity_suffix']
        perc_loss_col = intensity + conf['output']['perc_loss_suffix']
        # Percentage of losses
        asset_map[perc_loss_col] = asset_map.apply(calculate_perc_loss, axis=1,
                                                   depth_col=intensity_col,
                                                   loss_curves=loss_curves)


def main():
    loss_curves = load_loss_curves()
    asset_map = gpd.read_file(ASSETS_MAP_PATH)
    stats = apply_losses(asset_map, loss_curves)
    # Save map to file
    map_file_name = os.path.join(conf['input']['base_path'],
                                 conf['output']['file_name'])
    asset_map.to_file(map_file_name, driver='GPKG')


if __name__ == "__main__":
    sys.exit(main())
