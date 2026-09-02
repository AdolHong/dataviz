// Owner: Runtime-wide Renderer, worker, observer, and resource disposal.
Object.assign(datavizRuntime, {
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.cancelTransforms('Runtime disposed');
    this.inflightTransforms.clear();
    this.sectionAdapter?.dispose();
    this.viewAdapter?.dispose();
    this.presentationAdapter?.dispose();
    this.workerUrls.forEach(url => URL.revokeObjectURL(url));
    this.workerUrls.clear();
    this.interactionCache.clear();
    this.transformCacheEvidence.clear();
    this.controlImpactSignatures.clear();
    Object.values(this.interactiveAdapters).forEach(adapter => adapter.dispose());
  },
});
