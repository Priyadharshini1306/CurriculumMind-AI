// Force-directed layout that reserves room for node labels. The prerequisite graphs are sparse (many roots),
// where a hierarchical layout puts nearly every node on one row and the labels collide.
export const graphLayout = {
  name: 'cose',
  animate: false,
  fit: true,
  padding: 16,
  nodeDimensionsIncludeLabels: true,
  nodeRepulsion: () => 9000,
  idealEdgeLength: () => 55,
  edgeElasticity: () => 80,
  gravity: 1.4,
  numIter: 2000,
  componentSpacing: 25,
  randomize: true,
}
