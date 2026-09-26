//! wasm-bindgen bindings over `resolve_core::resolve::*` (Tasks 2-5) -- the browser-side twin of
//! the PyO3 bindings in `uedcli-native/src/lib.rs`. Zero new logic here; `resolve_actor_props` is
//! deliberately NOT exposed (spec §4).
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub struct WasmResolutionContext(resolve_core::ResolutionContext);

#[wasm_bindgen]
impl WasmResolutionContext {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self { Self(resolve_core::ResolutionContext::new()) }

    pub fn add_package(&mut self, name: &str, buf: &[u8]) -> Result<(), JsValue> {
        self.0.add_package(name, buf.to_vec()).map_err(|e| JsValue::from_str(&e.to_string()))
    }

    #[wasm_bindgen(js_name = packageImports)]
    pub fn package_imports(&self, name: &str) -> Result<Vec<String>, JsValue> {
        self.0.package_imports(name).map_err(|e| JsValue::from_str(&e.to_string()))
    }

    #[wasm_bindgen(js_name = resolveClass)]
    pub fn resolve_class(&mut self, fqcn: &str) -> Result<String, JsValue> {
        let r = resolve_core::resolve::resolve_class(fqcn, &mut self.0)
            .map_err(|e| JsValue::from_str(&e.to_string()))?;
        serde_json::to_string(&r).map_err(|e| JsValue::from_str(&e.to_string()))
    }
}
