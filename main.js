VSS.init({
    explicitNotifyLoaded: true,
    usePlatformScripts: true
});

VSS.ready(function () {
    console.log("Azure DevOps SDK Ready");

    const BASE_URL = "https://ai-aca-agt-prj0067566-wrkitm-bkd.orangeglacier-f13d9e59.eastus.azurecontainerapps.io";
    const GENERATE_URL = `${BASE_URL}/generate`;
    const CORS_TEST_URL = `${BASE_URL}/cors-test`;

    const webContext = VSS.getWebContext();
    const projectName = webContext.project ? webContext.project.name : "";
    const projectId = webContext.project ? webContext.project.id : "";

    console.log("Project Name:", projectName);
    console.log("Project Id:", projectId);

    // --------------------------
    // CORS TEST BUTTON
    // --------------------------
    const btnTest = document.getElementById("btnTestCors");

    if (btnTest) {
        btnTest.addEventListener("click", async function () {
            setStatus("Testing CORS...");

            try {
                const response = await fetch(CORS_TEST_URL, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json"
                    }
                });

                console.log("CORS Status:", response.status, response.statusText);

                const text = await response.text();
                console.log("CORS Raw Response:", text);

                let data = {};
                try {
                    data = JSON.parse(text);
                    console.log("CORS JSON:", data);
                } catch (err) {
                    console.warn("Not JSON:", text);
                }

                setStatus("CORS test completed. Check console.");

            } catch (error) {
                console.error("CORS test failed:", error);
                setStatus("CORS test failed.");
            }
        });
    }

    // --------------------------
    // GENERATE BUTTON
    // --------------------------
    document.getElementById("btnGenerate")
        .addEventListener("click", async function () {

            const notes = document.getElementById("notes").value.trim();
            const mode = document.getElementById("mode").value;
            const witType = document.getElementById("witType").value;

            if (!notes) {
                setStatus("Please enter notes before generating.");
                return;
            }

            if (!projectName || !projectId) {
                setStatus("Project context not found.");
                return;
            }

            setStatus("Generating work item content using AI...");

            try {
                const payload = {
                    notes: notes,
                    work_item_type: witType,
                    create_in_ado: true,
                    project_name: projectName,
                    project_id: projectId,
                    mode: mode
                };

                console.log("Generate URL:", GENERATE_URL);
                console.log("Payload:", payload);

                const response = await fetch(GENERATE_URL, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                });

                console.log("Generate Status:", response.status);

                const text = await response.text();
                console.log("Generate Raw Response:", text);

                let data = {};
                try {
                    data = JSON.parse(text);
                } catch (err) {
                    setStatus("Invalid JSON from backend.");
                    document.getElementById("apiResponse").textContent = text;
                    return;
                }

                document.getElementById("apiResponse").textContent =
                    JSON.stringify(data, null, 2);

                if (!response.ok) {
                    setStatus(data.detail || "Backend error");
                    return;
                }

                const generated = data.generated || data;

                if (generated.title)
                    document.getElementById("prevTitle").innerText = generated.title;

                if (generated.description)
                    document.getElementById("prevDesc").innerText = generated.description;

                if (generated.acceptanceCriteria) {
                    const list = document.getElementById("prevAc");
                    list.innerHTML = "";
                    generated.acceptanceCriteria.forEach(x => {
                        const li = document.createElement("li");
                        li.innerText = x;
                        list.appendChild(li);
                    });
                }

                if (generated.tasks) {
                    const list = document.getElementById("prevTasks");
                    list.innerHTML = "";
                    generated.tasks.forEach(x => {
                        const li = document.createElement("li");
                        li.innerText = x;
                        list.appendChild(li);
                    });
                }

                document.getElementById("btnCreate").disabled = false;
                document.getElementById("btnCopy").disabled = false;

                setStatus("Preview generated successfully.");

            } catch (error) {
                console.error("Generate failed:", error);
                setStatus("Error calling backend.");
                document.getElementById("apiResponse").textContent =
                    error.message;
            }
        });

    VSS.notifyLoadSucceeded();
});

function setStatus(message) {
    document.getElementById("status").innerText = message;
}
