// Browser primitives for VM clients; pending fixtures must not keep Node alive.
module.exports = {
  AbortController,
  clearTimeout,
  setTimeout(...args) {
    const timer = setTimeout(...args);
    timer.unref();
    return timer;
  },
};
