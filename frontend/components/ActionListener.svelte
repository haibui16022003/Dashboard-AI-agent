<script>
    /**
     * ActionListener — lives INSIDE Evidence.dev page content where it has
     * access to the shared InputStoreKey context. Wraps Dropdown components
     * as slot children inside a {#key} block so they re-mount when filters change.
     *
     * Usage in index.md:
     *   <ActionListener>
     *     <Dropdown ... />
     *   </ActionListener>
     */
    import { onMount, onDestroy } from "svelte";
    import { getInputContext } from "@evidence-dev/sdk/utils/svelte";

    const inputs = getInputContext();

    /** Incremented every time filters are applied — forces slot re-mount */
    let filterVersion = 0;

    function handleDashboardAction(event) {
        const payload = event.detail;
        console.log("[ActionListener] Received action:", payload);

        switch (payload.action) {
            case "set_filters":
                inputs.update(($inputs) => {
                    for (const { field, value } of payload.filters) {
                        console.log(`[ActionListener] Setting input "${field}" = "${value}"`);
                        $inputs[field] = {
                            value: value,
                            label: String(value),
                            rawValues: [{ value: value, label: String(value), selected: true }]
                        };
                    }
                    return $inputs;
                });
                filterVersion++;
                break;

            case "clear_filters":
                inputs.update(($inputs) => {
                    for (const field of payload.fields) {
                        console.log(`[ActionListener] Clearing input "${field}"`);
                        $inputs[field] = {
                            value: "%",
                            label: "All",
                            rawValues: [{ value: "%", label: "All", selected: true }]
                        };
                    }
                    return $inputs;
                });
                filterVersion++;
                break;
        }
    }

    onMount(() => {
        window.addEventListener("dashboard-action", handleDashboardAction);
        console.log("[ActionListener] Mounted — listening for dashboard-action events");
    });

    onDestroy(() => {
        window.removeEventListener("dashboard-action", handleDashboardAction);
    });
</script>

{#key filterVersion}
    <slot />
{/key}
