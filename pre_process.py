import numpy as np
from nilearn.input_data import NiftiSpheresMasker
from nilearn.connectome import ConnectivityMeasure
from typing import List, Union, Tuple, NoReturn
import networkx as nx
from feature_extraction import main_global_features
# from utils import *
import nilearn.datasets as datasets
from copy import deepcopy
from conf_pack.configuration import *
# dataloader ->

def load_scans(scan_paths: List[str], dir_path: str, data_type: str = 'correlation') -> \
        Union[List[np.ndarray], Tuple[List[np.ndarray], List[np.ndarray]]]:

    time_series_lst, corr_lst = [], []
    names = [os.path.basename(path) for path in scan_paths]

    if not default_params.getboolean('save_scans'):
        return load_saved_scans(dir_path=dir_path, data_type=data_type, names=names)

    for path in scan_paths:
        time_series = path_to_time_series(path)
        time_series_lst.append(time_series)

    save_numpy_lst(dir_path=dir_path, names=names, data_type='time_series', npy_to_save=time_series_lst)

    if data_type == 'time_series':
        return time_series_lst

    correlations = time_series_to_correlation(time_series_lst)

    save_numpy_lst(dir_path=dir_path, names=names, data_type='correlation', npy_to_save=correlations)

    if data_type == 'correlation':
        return correlations

    if data_type == 'both':
        return time_series_lst, correlations

    raise ValueError('Data type should be one of the [correlation, time_series, both]')


def load_saved_scans(dir_path, names: List[str], data_type: str) -> List[np.ndarray]:
    res = []
    for name in names:
        corr_path = os.path.join(dir_path, 'correlation', f'{name}.npy')
        time_series_path = os.path.join(dir_path, 'time_series', f'{name}.npy')
        if data_type == 'correlation':
            res.append(np.load(corr_path))
        elif data_type == 'time_series':
            res.append(np.load(time_series_path))
        elif data_type == 'both':
            res.append((np.load(corr_path), np.load(time_series_path)))
    return res


def save_numpy_lst(dir_path: str, names: List[str], data_type: str, npy_to_save: List[np.ndarray]) -> NoReturn:
    for name, npy_file in zip(names, npy_to_save):
        path_to_save = os.path.join(dir_path, data_type, name)
        np.save(f'{path_to_save}.npy', npy_file)


def path_to_time_series(path: str) -> np.ndarray:

    power_atlas = datasets.fetch_coords_power_2011()
    coords = np.vstack((power_atlas.rois['x'], power_atlas.rois['y'], power_atlas.rois['z'])).T
    spheres_masker = NiftiSpheresMasker(seeds=coords, smoothing_fwhm=4, radius=5., detrend=True, standardize=True,
                                        low_pass=0.1, high_pass=0.01, t_r=2.5)
    time_series = spheres_masker.fit_transform(path)
    time_series_cleaned = np.nan_to_num(time_series)
    return time_series_cleaned


def time_series_to_correlation(time_series_lts: List[np.ndarray], is_abs: bool = False) -> List[np.ndarray]:

    connectivity_measure = ConnectivityMeasure(kind='correlation')
    corr_mat_lst = connectivity_measure.fit_transform(time_series_lts)
    for corr_mat in corr_mat_lst:
        np.fill_diagonal(corr_mat, 0)
    if is_abs:
        corr_mat_lst = [np.abs(corr_mat) for corr_mat in corr_mat_lst]
    else:
        for corr_mat in corr_mat_lst:
            corr_mat[corr_mat < 0] = 0
    return corr_mat_lst


def build_graphs_from_corr(filter_type, corr_lst: List[np.ndarray], param) -> List[nx.Graph]:
    labels = get_labels()
    graphs = []
    for corr in corr_lst:
        graph = nx.from_numpy_matrix(corr, parallel_edges=False)
        nx.set_node_attributes(graph, dict(zip(range(len(labels)), labels)), 'label')
        graphs.append(graph)
    return filter_edges(filter_type, graphs, param)


def build_graphs_with_activations(scans_path: List[str], filter_type: str = 'density',
                                  param: float = 0.01) -> List[nx.Graph]:
    corr_lst, time_series_lst = load_scans(scans_path, 'both')
    graphs = build_graphs_from_corr(filter_type, corr_lst, param)
    for g, time_series in zip(graphs, time_series_lst):
        add_node_features(g, time_series)
    return graphs


def create_graphs_features_df(filter_type: str, corr_lst: List[np.ndarray], thresholds: Union[List[float], np.ndarray] ):
    os.makedirs(f'Graphs_pickle/{filter_type}', exist_ok=True)
    for thresh in thresholds:
        graphs = build_graphs_from_corr(filter_type=filter_type, corr_lst=corr_lst, param=thresh)
        features_df = main_global_features(graphs)
        features_df.to_pickle(os.path.join('Graphs_pickle', filter_type, f'graph_{thresh}.pkl'))


def add_node_features(g: nx.Graph, node_features: np.ndarray) -> nx.Graph:
    return g


def get_labels() -> List[str]:
    '''

    :return: labels of power atlas
    '''
    power = datasets.fetch_coords_power_2011()
    coordinates = np.vstack((power.rois['x'], power.rois['y'], power.rois['z'])).T
    labels = []
    for coordinate in coordinates:
        coordinate_str = np.array2string(coordinate)
        labels.append(coordinate_str)
    return labels


def filter_edges(filter_type: str, graphs: List[nx.Graph], param) -> List[nx.Graph]:
    mapping_filter = {'density': filter_by_dens, 'threshold': filter_by_threshold, 'pmfg': filter_by_pmfg}
    res = []
    for graph in graphs:
        res.append(mapping_filter[filter_type](graph, param))
    return res


def filter_by_threshold(graph: nx.Graph, threshold: float) -> nx.Graph:
    # g_copy = graph.copy()
    # edges = g_copy.edges
    # edges_to_remove = [edge for edge in edges if edges[edge]['weight'] < threshold]
    # g_copy.remove_edges_from(edges_to_remove)
    # return g_copy
    edges = graph.edges
    amount_of_edges = len([edge for edge in edges if edges[edge]['weight'] >= threshold])
    return filter_by_amount(graph, amount_of_edges)


def filter_by_pmfg(graph: nx.Graph, param: int = 0) -> nx.Graph:
    amount_of_nodes = len(graph.nodes)
    amount_of_edges = 3 * (amount_of_nodes - 2)
    sorted_edges = sort_graph_edges(graph)
    sorted_edges.reverse()
    pmfg = nx.Graph()
    nodes_with_attr = [(node, {'label': node['label']}) for node in list(graph.nodes())]
    pmfg.add_nodes_from(nodes_with_attr)

    for edge in sorted_edges:
        pmfg.add_edge(edge['source'], edge['dest'])
        if not nx.check_planarity(pmfg):
            pmfg.remove_edge(edge['source'], edge['dest'])
        if len(pmfg.edges()) == amount_of_edges:
            return pmfg


def filter_by_dens(graph: nx.Graph, density: float) -> nx.Graph:
    amount_of_nodes = len(graph.nodes())
    amount_of_edges = (amount_of_nodes * (amount_of_nodes - 1)) / 2
    return filter_by_amount(graph, int(amount_of_edges * density))


def filter_by_amount(graph: nx.Graph, amount_edges: int) -> nx.Graph:
    sorted_edges = sort_graph_edges(graph)
    norm_g = deepcopy(graph)
    norm_g.remove_edges_from(sorted_edges[:-amount_edges])
    return norm_g


def sort_graph_edges(graph: nx.Graph) -> nx.edges:
    edges = sorted(graph.edges(data=True), key=lambda t: t[2].get('weight', 1))
    return edges






