import * as tableCore from "@tanstack/table-core";
import { FlexRender } from "@tanstack/table-core/flex-render";
import { storeReactivityBindings } from "@tanstack/table-core/store-reactivity-bindings";

globalThis.datavizTanStackTable = Object.freeze({
  ...tableCore,
  FlexRender,
  storeReactivityBindings,
  version: "9.2.4",
});
