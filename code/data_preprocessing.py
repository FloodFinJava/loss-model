# -*- coding: utf-8 -*-

import sys
import io
import os

import toml
import geopandas as gpd
import matplotlib.pyplot as plt

from grass_session import Session
from grass.script import core as gscript

CONF_FILE = "conf.toml"

GRASS_DB = '/tmp'
CRS = "EPSG:4326"

# Load configuration data from the toml file as a dict
with open(CONF_FILE, 'r') as toml_file:
    toml_string = toml_file.read()
conf = toml.loads(toml_string)


def clean_osm(osm_gpkg, amenity_cat, col_keep):
    gdf = gpd.read_file(osm_gpkg)
    # Select only the categories of interest
    gdf_select = gdf.loc[gdf.amenity.isin(amenity_cat)]
    # Drop unwanted columns
    current_col = list(gdf_select.columns.values)
    col_drop = [i for i in current_col if i not in col_keep]
    return gdf_select.drop(columns=col_drop)


def get_flooded_assets(asset_map, flood_maps_dict, output_map):
    """Use GRASS to get max flood depth value at each asset
    """
    with Session(gisdb="/tmp", location="loss_model", create_opts=CRS):
        # import maps
        vect_map = 'assets'
        gscript.run_command('v.import', input=asset_map, output=vect_map, overwrite=True)
        for return_period, flood_map in flood_maps_dict.items():
            map_name = "flood_map_{}".format(return_period)
            gscript.run_command('r.external', input=flood_map, output=map_name,
                                overwrite=True)
            # set computational extent
            gscript.run_command('g.region', raster=map_name, vector=vect_map)
            # Set negative depth values to zero
            map_null = map_name + "_fix"
            exp = "{o} = if({i} <= 0, 0, {i})".format(o=map_null, i=map_name)
            gscript.run_command('r.mapcalc', expression=exp, overwrite=True)
            # write raster stats as column in the vector
            gscript.run_command('v.rast.stats', map=vect_map, raster=map_null,
                                column_prefix=return_period, method='maximum',
                                overwrite=True)
        # export new map
        gscript.run_command('v.out.ogr', input=vect_map, format='GPKG',
                            output=output_map, overwrite=True)


def populate_value_and_curve(asset_map, col_value, col_curve):
    gdf = gpd.read_file(asset_map)
    # set arbitrary values
    high_value = ('hospital', 'university', 'college', 'research_institute')
    gdf.loc[gdf.amenity.isin(high_value), col_value] = 700000
    gdf.loc[~gdf.amenity.isin(high_value), col_value] = 100000
    # set arbitrary loss curves
    high_rise =  ('university', 'college', 'library', 'hospital')
    gdf.loc[gdf.amenity.isin(high_rise), col_curve] = "high_rise"
    gdf.loc[~gdf.amenity.isin(high_rise), col_curve] = "low_rise"
    # Remove current file and write it again with the new columns
    os.remove(asset_map)
    gdf.to_file(asset_map, driver='GPKG')


def main():
    # Get info from configuration file
    base_path = conf['input']['base_path']
    osm_input = os.path.join(base_path, conf['input']['osm']['raw'])
    amenity_cats = conf['input']['osm']['amenity_cat']
    col_keep = conf['input']['osm']['col_keep']
    osm_clean = os.path.join(base_path, conf['input']['osm']['clean'])
    flooded_assets_map = os.path.join(base_path, conf['input']['assets']['path'],
                                      conf['input']['assets']['map_name'])
    col_value = conf['input']['assets']['value']
    col_curve = conf['input']['assets']['loss_curve']
    # Save cleaned map from osm
    # gdf_clean = clean_osm(osm_input, amenity_cats, col_keep)
    # gdf_clean.to_file(osm_clean, driver='GPKG')

    # get the flooded depth for each raster map
    flood_maps_dict = {}
    return_periods = conf['input']['flood_map']['intensities']
    for return_period in return_periods:
        map_name = "{p}{rp}{s}".format(p=conf['input']['flood_map']['prefix'],
                                       rp=return_period,
                                       s=conf['input']['flood_map']['suffix'])
        map_path = os.path.join(conf['input']['base_path'],
                                conf['input']['flood_map']['path'],
                                map_name)
        flood_maps_dict[return_period] = map_path
    get_flooded_assets(osm_clean, flood_maps_dict, flooded_assets_map)

    # Add asset value and loss_curves
    populate_value_and_curve(flooded_assets_map, col_value, col_curve)



if __name__ == "__main__":
    sys.exit(main())
