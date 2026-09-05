import QtQuick
import Quickshell
import "Plugin" as Plugin
import "Plugin/Model.js" as Model

ShellRoot {
    Plugin.Panel {
        id: panel

        function bootstrap(force) {
        }

        function loadDay() {
        }

        function loadCalendarRange() {
        }

        function persist(values) {
        }

        settings: ({
            "workspaceId": 4,
            "classifier": "off"
        })
        selectedWorkspaceId: 4
        dayLoaded: true
        calendarLoaded: true
        Component.onCompleted: {
            dayBlocks = Model.prepareBlocks([{
                "start": "2026-09-05T12:00:00Z",
                "end": "2026-09-05T12:10:00Z",
                "seconds": 600,
                "label": "Smoke test",
                "topics": [{
                    "name": "Smoke test",
                    "seconds": 600
                }],
                "apps": []
            }], []);
        }
    }

    Timer {
        property int step: 0

        interval: 200
        repeat: true
        running: true
        onTriggered: {
            if (step === 0) {
                panel.setScope("day");
                panel.classifier = "off";
                panel.requestPending = true;
                panel.enrichmentActive = {
                    "classify": false
                };
                panel.finishEnrichment(JSON.stringify({
                    "ok": true,
                    "data": {
                        "workspace_id": 4,
                        "date": panel.dayDate,
                        "generation": panel.dayGeneration,
                        "blocks": [{
                            "index": 0,
                            "signature": Model.enrichmentSnapshot(panel.dayBlocks[0]),
                            "projects": []
                        }],
                        "results": [{
                            "index": 0,
                            "description": "Background wording"
                        }]
                    }
                }));
                if (!panel.requestPending || panel.dayBlocks[0].description !== "Background wording")
                    throw new Error("background isolation: pending=" + panel.requestPending + ", workspace=" + panel.selectedWorkspaceId + ", description=" + panel.dayBlocks[0].description);

                panel.requestPending = false;
            }
            if (step === 1) {
                panel.dayBlocks[0].description = "Retained draft";
                panel.dayBlocks[0].tokenDraft = "@retained/task";
                panel.dayBlocks[0].editing = true;
                panel.slotChanged();
                panel.setScope("cal");
            }
            if (step === 2)
                panel.setScope("day");

            if (step === 3) {
                if (panel.dayBlocks[0].description !== "Retained draft" || panel.dayBlocks[0].tokenDraft !== "@retained/task")
                    throw new Error("draft lost");

                panel.enrichmentActive = {
                    "classify": false
                };
                panel.finishEnrichment(JSON.stringify({
                    "ok": true,
                    "data": {
                        "workspace_id": 5,
                        "date": panel.dayDate,
                        "generation": panel.dayGeneration,
                        "blocks": [{
                            "index": 0,
                            "signature": Model.enrichmentSnapshot(panel.dayBlocks[0]),
                            "projects": []
                        }],
                        "results": [{
                            "index": 0,
                            "description": "Wrong workspace"
                        }]
                    }
                }));
                if (panel.dayBlocks[0].description !== "Retained draft")
                    throw new Error("stale workspace response applied");

                panel.setScope("timer");
                console.log("TOGGL_SMOKE_OK: scopes and drafts");
                Qt.quit();
            }
            step++;
        }
    }

}
