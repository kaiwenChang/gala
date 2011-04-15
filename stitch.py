#!/usr/bin/env python

import sys, os, argparse
from agglo import Rag
from imio import read_image_stack
from numpy import zeros, bool, hstack, newaxis
from scipy.ndimage.filters import median_filter, gaussian_filter
from scipy.ndimage.measurements import label

def is_one_to_one_mapping(array1, array2):
    pixelmap = dict()
    for p1, p2 in zip(array1.ravel(), array2.ravel()):
        try:
            pixelmap[p1].add(p2)
        except KeyError:
            pixelmap[p1] = set([p2])
    return array([len(m)==1 for m in pixelmap.values()]).all()

def crop_probs_and_ws(crop, probs, ws):
    xmin, xmax, ymin, ymax, zmin, zmax = crop
    probs = probs[xmin:xmax, ymin:ymax, zmin:zmax]
    ws = label(ws[xmin:xmax, ymin:ymax, zmin:zmax])
    return probs, ws

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Segment a volume using a superpixel-to-RAG model.'
    )
    parser.add_argument('fin', nargs='+', 
        help='The boundary probability map file(s).'
    )
    parser.add_argument('fout', 
        help='The output filename (use - for stdout)'
    )
    parser.add_argument('-I', '--invert-image', action='store_true',
        default=False,
        help='Invert the probabilities before segmenting.'
    )
    parser.add_argument('-x', '--xy-crop', action=eval, default=[None]*4,
        help='Specify a crop in the first and second array dimensions.'
    )
    parser.add_argument('-w', '--watershed', metavar='WS_FN',
        type=read_image_stack_single_arg,
        help='Use a precomputed watershed volume from file.'
    )
    parser.add_argument('-t', '--thresholds', nargs='+', default=[128],
        type=float, metavar='FLOAT',
        help='''The agglomeration thresholds. One output file will be written
            for each threshold.'''
    )
    parser.add_argument('-T', '--thickness', type=int, default=250,
        help='How thick each substack should be.'
    )
    parser.add_argument('-m', '--median-filter', action='store_true', 
        default=False, help='Run a median filter on the input image.'
    )
    parser.add_argument('-g', '--gaussian-filter', type=float, metavar='SIGMA',
        help='Apply a gaussian filter before watershed.'
    )
    parser.add_argument('-P', '--show-progress', action='store_true',
        default=True, help='Show a progress bar for the agglomeration.'
    )
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
        help='Print runtime information about execution.'
    )
    args = parser.parse_args()

    probs = read_image_stack(*args.fin)
    if args.invert_image:
        probs = probs.max() - probs
    if args.median_filter:
        probs = median_filter(probs, 3)
    elif args.gaussian_filter is not None:
        probs = gaussian_filter(probs, args.gaussian_filter)

    if args.watershed is None:
        args.watershed = watershed(probs, show_progress=args.show_progress)

    thickness = args.thickness
    zcrop1 = [0,thickness]
    overlaps = [2**i+1 for i in range(1,8)]
    results_table = zeros([len(args.thresholds), len(range(1,8))], dtype=bool)
    for j, overlap in enumerate(overlaps):
        zcrop2 = [thickness-overlap, 2*thickness-overlap]
        probs1, ws1 = crop_probs_and_ws(args.xy_crop+zcrop1, probs, ws)
        probs2, ws2 = crop_probs_and_ws(args.xy_crop+zcrop2, probs, ws)
        g1 = Rag(probs1, ws1, show_progress=args.show_progress)
        g2 = Rag(probs2, ws2, show_progress=args.show_progress)
        for i, t in enumerate(args.thresholds):
            g1.agglomerate(t)
            g2.agglomerate(t)
            results_table[i,j] = is_one_to_one_mapping(
                                    g1.segmentation[...,-overlap/2-1], 
                                    g2.segmentation[...,overlap/2])
    results_table = hstack([array(args.thresholds)[:,newaxis], results_table)
    results_table = \
        vstack([array([0]+overlaps), results_table, results_table.all(axis=0)])
    savetxt(args.fout, results_table, delimiter='\t')

