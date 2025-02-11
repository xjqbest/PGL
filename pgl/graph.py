# Copyright (c) 2019 PaddlePaddle Authors. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
    This package implement Graph structure for handling graph data.
"""

import numpy as np
import pickle as pkl
import time
import pgl.graph_kernel as graph_kernel

__all__ = ['Graph', 'SubGraph']


def _hide_num_nodes(shape):
    """Set the first dimension as unknown
    """
    shape = list(shape)
    shape[0] = None
    return shape


class EdgeIndex(object):
    """Indexing edges for fast graph queries

    Sorted edges and represent edges in compressed style like csc_matrix or csr_matrix.

    Args:
        u: A list of node id to be compressed.
        v: A list of node id that are connected with u.
        num_nodes: The exactive number of nodes.
    """

    def __init__(self, u, v, num_nodes):
        self._v, self._eid, self._degree, self._sorted_u,\
                self._sorted_v, self._sorted_eid = graph_kernel.build_index(u, v, num_nodes)

    @property
    def degree(self):
        """Return the degree of nodes.
        """
        return self._degree

    @property
    def v(self):
        """Return the compressed v.
        """
        return self._v

    @property
    def eid(self):
        """Return the edge id.
        """
        return self._eid

    def triples(self):
        """Return the sorted (u, v, eid) tuples.
        """
        return self._sorted_u, self._sorted_v, self._sorted_eid


class Graph(object):
    """Implementation of graph structure in pgl.

    This is a simple implementation of graph structure in pgl.

    Args:
        num_nodes: number of nodes in a graph
        edges: list of (u, v) tuples
        node_feat (optional): a dict of numpy array as node features
        edge_feat (optional): a dict of numpy array as edge features (should
                                have consistent order with edges)

    Examples:

        .. code-block:: python

            import numpy as np
            num_nodes = 5
            edges = [ (0, 1), (1, 2), (3, 4)]
            feature = np.random.randn(5, 100)
            edge_feature = np.random.randn(3, 100)
            graph = Graph(num_nodes=num_nodes,
                        edges=edges,
                        node_feat={
                            "feature": feature
                        },
                        edge_feat={
                            "edge_feature": edge_feature
                        })

    """

    def __init__(self, num_nodes, edges=None, node_feat=None, edge_feat=None):
        if node_feat is not None:
            self._node_feat = node_feat
        else:
            self._node_feat = {}

        if edge_feat is not None:
            self._edge_feat = edge_feat
        else:
            self._edge_feat = {}

        if isinstance(edges, np.ndarray):
            if edges.dtype != "int64":
                edges = edges.astype("int64")
        else:
            edges = np.array(edges, dtype="int64")

        self._edges = edges
        self._num_nodes = num_nodes

        if len(edges) == 0:
            raise ValueError("The Graph have no edges.")

        self._adj_src_index = None
        self._adj_dst_index = None

    @property
    def adj_src_index(self):
        """Return an EdgeIndex object for src.
        """
        if self._adj_src_index is None:
            self._adj_src_index = EdgeIndex(
                u=self._edges[:, 0],
                v=self._edges[:, 1],
                num_nodes=self._num_nodes)
        return self._adj_src_index

    @property
    def adj_dst_index(self):
        """Return an EdgeIndex object for dst.
        """
        if self._adj_dst_index is None:
            self._adj_dst_index = EdgeIndex(
                u=self._edges[:, 1],
                v=self._edges[:, 0],
                num_nodes=self._num_nodes)
        return self._adj_dst_index

    @property
    def edge_feat(self):
        """Return a dictionary of edge features.
        """
        return self._edge_feat

    @property
    def node_feat(self):
        """Return a dictionary of node features.
        """
        return self._node_feat

    @property
    def num_edges(self):
        """Return the number of edges.
        """
        return len(self._edges)

    @property
    def num_nodes(self):
        """Return the number of nodes.
        """
        return self._num_nodes

    @property
    def edges(self):
        """Return all edges in numpy.ndarray with shape (num_edges, 2).
        """
        return self._edges

    def sorted_edges(self, sort_by="src"):
        """Return sorted edges with different strategies.

        This function will return sorted edges with different strategy.
        If :code:`sort_by="src"`, then edges will be sorted by :code:`src`
        nodes and otherwise :code:`dst`.

        Args:
            sort_by: The type for sorted edges. ("src" or "dst")

        Return:
            A tuple of (sorted_src, sorted_dst, sorted_eid).
        """
        if sort_by not in ["src", "dst"]:
            raise ValueError("sort_by should be in 'src' or 'dst'.")
        if sort_by == 'src':
            src, dst, eid = self.adj_src_index.triples()
        else:
            dst, src, eid = self.adj_dst_index.triples()
        return src, dst, eid

    @property
    def nodes(self):
        """Return all nodes id from 0 to :code:`num_nodes - 1`
        """
        return np.arange(self._num_nodes, dtype="int64")

    def indegree(self, nodes=None):
        """Return the indegree of the given nodes

        This function will return indegree of given nodes.

        Args:
            nodes: Return the indegree of given nodes,
                   if nodes is None, return indegree for all nodes

        Return:
            A numpy.ndarray as the given nodes' indegree.
        """
        if nodes is None:
            return self.adj_dst_index.degree
        else:
            return self.adj_dst_index.degree[nodes]

    def outdegree(self, nodes=None):
        """Return the outdegree of the given nodes.

        This function will return outdegree of given nodes.

        Args:
            nodes: Return the outdegree of given nodes,
                   if nodes is None, return outdegree for all nodes

        Return:
            A numpy.array as the given nodes' outdegree.
        """
        if nodes is None:
            return self.adj_src_index.degree
        else:
            return self.adj_src_index.degree[nodes]

    def successor(self, nodes=None, return_eids=False):
        """Find successor of given nodes.

        This function will return the successor of given nodes.

        Args:
            nodes: Return the successor of given nodes,
                   if nodes is None, return successor for all nodes.

            return_eids: If True return nodes together with corresponding eid

        Return:
            Return a list of numpy.ndarray and each numpy.ndarray represent a list
            of successor ids for given nodes. If :code:`return_eids=True`, there will
            be an additional list of numpy.ndarray and each numpy.ndarray represent
            a list of eids that connected nodes to their successors.

        Example:
            .. code-block:: python

                import numpy as np
                num_nodes = 5
                edges = [ (0, 1), (1, 2), (3, 4)]
                graph = Graph(num_nodes=num_nodes,
                        edges=edges)
                succ, succ_eid = graph.successor(return_eids=True)

            This will give output.

            .. code-block:: python

                succ:
                      [[1],
                       [2],
                       [],
                       [4],
                       []]

                succ_eid:
                      [[0],
                       [1],
                       [],
                       [2],
                       []]

        """
        if nodes is None:
            if return_eids:
                return self.adj_src_index.v, self.adj_src_index.eid
            else:
                return self.adj_src_index.v
        else:
            if return_eids:
                return self.adj_src_index.v[nodes], self.adj_src_index.eid[
                    nodes]
            else:
                return self.adj_src_index.v[nodes]

    def sample_successor(self,
                         nodes,
                         max_degree,
                         return_eids=False,
                         shuffle=False):
        """Sample successors of given nodes.

        Args:
            nodes: Given nodes whose successors will be sampled.

            max_degree: The max sampled successors for each nodes.

            return_eids: Whether to return the corresponding eids.

        Return:

            Return a list of numpy.ndarray and each numpy.ndarray represent a list
            of sampled successor ids for given nodes. If :code:`return_eids=True`, there will
            be an additional list of numpy.ndarray and each numpy.ndarray represent
            a list of eids that connected nodes to their successors.
        """

        node_succ = self.successor(nodes, return_eids=return_eids)
        if return_eids:
            node_succ, node_succ_eid = node_succ

        if nodes is None:
            nodes = self.nodes

        node_succ = node_succ.tolist()

        if return_eids:
            node_succ_eid = node_succ_eid.tolist()

        if return_eids:
            return graph_kernel.sample_subset_with_eid(
                node_succ, node_succ_eid, max_degree, shuffle)
        else:
            return graph_kernel.sample_subset(node_succ, max_degree, shuffle)

    def predecessor(self, nodes=None, return_eids=False):
        """Find predecessor of given nodes.

        This function will return the predecessor of given nodes.

        Args:
            nodes: Return the predecessor of given nodes,
                   if nodes is None, return predecessor for all nodes.

            return_eids: If True return nodes together with corresponding eid

        Return:
            Return a list of numpy.ndarray and each numpy.ndarray represent a list
            of predecessor ids for given nodes. If :code:`return_eids=True`, there will
            be an additional list of numpy.ndarray and each numpy.ndarray represent
            a list of eids that connected nodes to their predecessors.

        Example:
            .. code-block:: python

                import numpy as np
                num_nodes = 5
                edges = [ (0, 1), (1, 2), (3, 4)]
                graph = Graph(num_nodes=num_nodes,
                        edges=edges)
                pred, pred_eid = graph.predecessor(return_eids=True)

            This will give output.

            .. code-block:: python

                pred:
                      [[],
                       [0],
                       [1],
                       [],
                       [3]]

                pred_eid:
                      [[],
                       [0],
                       [1],
                       [],
                       [2]]

        """
        if nodes is None:
            if return_eids:
                return self.adj_dst_index.v, self.adj_dst_index.eid
            else:
                return self.adj_dst_index.v
        else:
            if return_eids:
                return self.adj_dst_index.v[nodes], self.adj_dst_index.eid[
                    nodes]
            else:
                return self.adj_dst_index.v[nodes]

    def sample_predecessor(self,
                           nodes,
                           max_degree,
                           return_eids=False,
                           shuffle=False):
        """Sample predecessor of given nodes.

        Args:
            nodes: Given nodes whose predecessor will be sampled.

            max_degree: The max sampled predecessor for each nodes.

            return_eids: Whether to return the corresponding eids.

        Return:

            Return a list of numpy.ndarray and each numpy.ndarray represent a list
            of sampled predecessor ids for given nodes. If :code:`return_eids=True`, there will
            be an additional list of numpy.ndarray and each numpy.ndarray represent
            a list of eids that connected nodes to their predecessors.
        """
        node_pred = self.predecessor(nodes, return_eids=return_eids)
        if return_eids:
            node_pred, node_pred_eid = node_pred

        if nodes is None:
            nodes = self.nodes

        node_pred = node_pred.tolist()

        if return_eids:
            node_pred_eid = node_pred_eid.tolist()

        if return_eids:
            return graph_kernel.sample_subset_with_eid(
                node_pred, node_pred_eid, max_degree, shuffle)
        else:
            return graph_kernel.sample_subset(node_pred, max_degree, shuffle)

    def node_feat_info(self):
        """Return the information of node feature for GraphWrapper.

        This function return the information of node features. And this
        function is used to help constructing GraphWrapper

        Return:
            A list of tuple (name, shape, dtype) for all given node feature.

        Examples:

            .. code-block:: python

                import numpy as np
                num_nodes = 5
                edges = [ (0, 1), (1, 2), (3, 4)]
                feature = np.random.randn(5, 100)
                graph = Graph(num_nodes=num_nodes,
                        edges=edges,
                        node_feat={
                            "feature": feature
                        })
                print(graph.node_feat_info())

            The output will be:

            .. code-block:: python

                [("feature", [None, 100], "float32")]

        """
        node_feat_info = []
        for key, value in self._node_feat.items():
            node_feat_info.append(
                (key, _hide_num_nodes(value.shape), value.dtype))
        return node_feat_info

    def edge_feat_info(self):
        """Return the information of edge feature for GraphWrapper.

        This function return the information of edge features. And this
        function is used to help constructing GraphWrapper

        Return:
            A list of tuple (name, shape, dtype) for all given edge feature.

        Examples:

            .. code-block:: python

                import numpy as np
                num_nodes = 5
                edges = [ (0, 1), (1, 2), (3, 4)]
                feature = np.random.randn(3, 100)
                graph = Graph(num_nodes=num_nodes,
                        edges=edges,
                        edge_feat={
                            "feature": feature
                        })
                print(graph.edge_feat_info())

            The output will be:

            .. code-block:: python

                [("feature", [None, 100], "float32")]

        """
        edge_feat_info = []
        for key, value in self._edge_feat.items():
            edge_feat_info.append(
                (key, _hide_num_nodes(value.shape), value.dtype))
        return edge_feat_info

    def subgraph(self, nodes, eid=None, edges=None):
        """Generate subgraph with nodes and edge ids.

        This function will generate a :code:`pgl.graph.Subgraph` object and
        copy all corresponding node and edge features. Nodes and edges will
        be reindex from 0. Eid and edges can't both be None.

        WARNING: ALL NODES IN EID MUST BE INCLUDED BY NODES

        Args:
            nodes: Node ids which will be included in the subgraph.

            eid (optional): Edge ids which will be included in the subgraph.

            edges (optional): Edge(src, dst) list which will be included in the subgraph.

        Return:
            A :code:`pgl.graph.Subgraph` object.
        """
        reindex = {}

        for ind, node in enumerate(nodes):
            reindex[node] = ind

        if eid is None and edges is None:
            raise ValueError("Eid and edges can't be None at the same time.")

        if edges is None:
            edges = self._edges[eid]
        else:
            edges = np.array(edges, dtype="int64")

        sub_edges = graph_kernel.map_edges(
            np.arange(
                len(edges), dtype="int64"), edges, reindex)

        sub_edge_feat = {}
        for key, value in self._edge_feat.items():
            if eid is None:
                raise ValueError("Eid can not be None with edge features.")
            sub_edge_feat[key] = value[eid]

        sub_node_feat = {}
        for key, value in self._node_feat.items():
            sub_node_feat[key] = value[nodes]

        subgraph = SubGraph(
            num_nodes=len(nodes),
            edges=sub_edges,
            node_feat=sub_node_feat,
            edge_feat=sub_edge_feat,
            reindex=reindex)
        return subgraph

    def node_batch_iter(self, batch_size, shuffle=True):
        """Node batch iterator

        Iterate all node by batch.

        Args:
            batch_size: The batch size of each batch of nodes.

            shuffle: Whether shuffle the nodes.

        Return:
            Batch iterator
        """
        perm = np.arange(self._num_nodes, dtype="int64")
        if shuffle:
            np.random.shuffle(perm)
        start = 0
        while start < self._num_nodes:
            yield perm[start:start + batch_size]
            start += batch_size

    def sample_nodes(self, sample_num):
        """Sample nodes from the graph

        This function helps to sample nodes from all nodes.
        Nodes might be duplicated.

        Args:
            sample_num: The number of samples

        Return:
            A list of nodes
        """
        return np.random.randint(low=0, high=self._num_nodes, size=sample_num)

    def sample_edges(self, sample_num, replace=False):
        """Sample edges from the graph

        This function helps to sample edges from all edges.

        Args:
            sample_num: The number of samples
            replace: boolean, Whether the sample is with or without replacement.

        Return:
            (u, v), eid 
            each is a numy.array with the same shape.
        """

        sampled_eid = np.random.choice(
            np.arange(self._edges.shape[0]), sample_num, replace=replace)
        return self._edges[sampled_eid], sampled_eid

    def has_edges_between(self, u, v):
        """Check whether some edges is in graph.

        Args:
            u: a numpy.array of src nodes ID.
            v: a numpy.array of dst nodes ID.

        Return:
            exists: A numpy.array of bool, with the same shape with `u` and `v`,
                exists[i] is True if (u[i], v[i]) is a edge in graph, Flase otherwise.
        """
        assert u.shape[0] == v.shape[0], "u and v must have the same shape"
        exists = np.logical_and(u < self.num_nodes, v < self.num_nodes)
        exists_idx = np.arange(u.shape[0])[exists]
        for idx, succ in zip(exists_idx, self.successor(u[exists])):
            exists[idx] = v[idx] in succ
        return exists

    def random_walk(self, nodes, max_depth):
        """Implement of random walk.

        This function get random walks path for given nodes and depth.

        Args:
            nodes: Walk starting from nodes
            max_depth: Max walking depth

        Return:
            A list of walks.
        """
        walk = []
        # init
        for node in nodes:
            walk.append([node])

        cur_walk_ids = np.arange(0, len(nodes))
        cur_nodes = np.array(nodes)
        for l in range(max_depth):
            # select the walks not end
            outdegree = self.outdegree(cur_nodes)
            mask = (outdegree != 0)
            if np.any(mask):
                cur_walk_ids = cur_walk_ids[mask]
                cur_nodes = cur_nodes[mask]
                outdegree = outdegree[mask]
            else:
                # stop when all nodes have no successor
                break
            succ = self.successor(cur_nodes)
            sample_index = np.floor(
                np.random.rand(outdegree.shape[0]) * outdegree).astype("int64")

            nxt_cur_nodes = []
            for s, ind, walk_id in zip(succ, sample_index, cur_walk_ids):
                walk[walk_id].append(s[ind])
                nxt_cur_nodes.append(s[ind])
            cur_nodes = np.array(nxt_cur_nodes)
        return walk

    def node2vec_random_walk(self, nodes, max_depth, p=1.0, q=1.0):
        """Implement of node2vec stype random walk.

        Reference paper: https://cs.stanford.edu/~jure/pubs/node2vec-kdd16.pdf.

        Args:
            nodes: Walk starting from nodes
            max_depth: Max walking depth
            p: Return parameter
            q: In-out parameter

        Return:
            A list of walks.
        """
        if p == 1. and q == 1.:
            return self.random_walk(nodes, max_depth)

        walk = []
        # init
        for node in nodes:
            walk.append([node])

        cur_walk_ids = np.arange(0, len(nodes))
        cur_nodes = np.array(nodes)
        prev_nodes = np.array([-1] * len(nodes), dtype="int64")
        prev_succs = np.array([[]] * len(nodes), dtype="int64")
        for l in range(max_depth):
            # select the walks not end
            outdegree = self.outdegree(cur_nodes)
            mask = (outdegree != 0)
            if np.any(mask):
                cur_walk_ids = cur_walk_ids[mask]
                cur_nodes = cur_nodes[mask]
                prev_nodes = prev_nodes[mask]
                prev_succs = prev_succs[mask]
            else:
                # stop when all nodes have no successor
                break
            cur_succs = self.successor(cur_nodes)
            num_nodes = cur_nodes.shape[0]
            nxt_nodes = np.zeros(num_nodes, dtype="int64")

            for idx, (succ, prev_succ, walk_id, prev_node) in enumerate(
                    zip(cur_succs, prev_succs, cur_walk_ids, prev_nodes)):

                sampled_succ = graph_kernel.node2vec_sample(succ, prev_succ,
                                                            prev_node, p, q)
                walk[walk_id].append(sampled_succ)
                nxt_nodes[idx] = sampled_succ

            prev_nodes, prev_succs = cur_nodes, cur_succs
            cur_nodes = nxt_nodes
        return walk


class SubGraph(Graph):
    """Implementation of SubGraph in pgl.

    Subgraph is inherit from :code:`Graph`. The best way to construct subgraph
    is to use :code:`Graph.subgraph` methods to generate Subgraph object.

    Args:
        num_nodes: number of nodes in a graph
        edges: list of (u, v) tuples
        node_feat (optional): a dict of numpy array as node features
        edge_feat (optional): a dict of numpy array as edge features (should
                                have consistent order with edges)
        reindex: A dictionary that maps parent graph node id to subgraph node id.
    """

    def __init__(self,
                 num_nodes,
                 edges=None,
                 node_feat=None,
                 edge_feat=None,
                 reindex=None):
        super(SubGraph, self).__init__(
            num_nodes=num_nodes,
            edges=edges,
            node_feat=node_feat,
            edge_feat=edge_feat)
        if reindex is None:
            reindex = {}
        self._from_reindex = reindex
        self._to_reindex = {u: v for v, u in reindex.items()}

    def reindex_from_parrent_nodes(self, nodes):
        """Map the given parent graph node id to subgraph id.

        Args:
            nodes: A list of nodes from parent graph.

        Return:
            A list of subgraph ids.
        """
        return graph_kernel.map_nodes(nodes, self._from_reindex)

    def reindex_to_parrent_nodes(self, nodes):
        """Map the given subgraph node id to parent graph id.

        Args:
            nodes: A list of nodes in this subgraph.

        Return:
            A list of node ids in parent graph.
        """
        return graph_kernel.map_nodes(nodes, self._to_reindex)
