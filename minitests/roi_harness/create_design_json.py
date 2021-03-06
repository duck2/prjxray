import xjson
import csv
import argparse
import sys
import fasm
from prjxray.db import Database
from prjxray.roi import Roi
from prjxray.util import get_db_root


def set_port_wires(ports, name, pin, wires_outside_roi):
    for port in ports:
        if name == port['name']:
            port['wires_outside_roi'] = wires_outside_roi
            assert port['pin'] == pin
            return

    assert False, name


def main():
    parser = argparse.ArgumentParser(
        description=
        "Creates design.json from output of ROI generation tcl script.")
    parser.add_argument('--design_txt', required=True)
    parser.add_argument('--design_info_txt', required=True)
    parser.add_argument('--pad_wires', required=True)
    parser.add_argument('--design_fasm', required=True)

    args = parser.parse_args()

    design_json = {}
    design_json['ports'] = []
    design_json['info'] = {}
    with open(args.design_txt) as f:
        for d in csv.DictReader(f, delimiter=' '):
            design_json['ports'].append(d)

    with open(args.design_info_txt) as f:
        for l in f:
            name, value = l.strip().split(' = ')

            design_json['info'][name] = int(value)

    db = Database(get_db_root())
    grid = db.grid()

    roi = Roi(
        db=db,
        x1=design_json['info']['GRID_X_MIN'],
        y1=design_json['info']['GRID_Y_MIN'],
        x2=design_json['info']['GRID_X_MAX'],
        y2=design_json['info']['GRID_Y_MAX'],
    )

    with open(args.pad_wires) as f:
        for l in f:
            parts = l.strip().split(' ')
            name = parts[0]
            pin = parts[1]
            wires = parts[2:]

            wires_outside_roi = []

            for wire in wires:
                tile = wire.split('/')[0]

                loc = grid.loc_of_tilename(tile)

                if not roi.tile_in_roi(loc):
                    wires_outside_roi.append(wire)

            set_port_wires(design_json['ports'], name, pin, wires_outside_roi)

    frames_in_use = set()
    for tile in roi.gen_tiles():
        gridinfo = grid.gridinfo_at_tilename(tile)

        for bit in gridinfo.bits.values():
            frames_in_use.add(bit.base_address)

    required_features = []
    for fasm_line in fasm.parse_fasm_filename(args.design_fasm):
        if fasm_line.annotations:
            for annotation in fasm_line.annotations:
                if annotation.name != 'unknown_segment':
                    continue

                unknown_base_address = int(annotation.value, 0)

                assert unknown_base_address not in frames_in_use, "Found unknown bit in base address 0x{:08x}".format(
                    unknown_base_address)

        if not fasm_line.set_feature:
            continue

        tile = fasm_line.set_feature.feature.split('.')[0]

        loc = grid.loc_of_tilename(tile)
        gridinfo = grid.gridinfo_at_tilename(tile)

        base_address_in_roi = False
        for bit in gridinfo.bits.values():
            if bit.base_address in frames_in_use:
                base_address_in_roi = True

        not_in_roi = not roi.tile_in_roi(loc)

        if not_in_roi and base_address_in_roi:
            required_features.append(fasm_line)

    design_json['required_features'] = fasm.fasm_tuple_to_string(
        required_features, canonical=True).split('\n')

    xjson.pprint(sys.stdout, design_json)


if __name__ == '__main__':
    main()
