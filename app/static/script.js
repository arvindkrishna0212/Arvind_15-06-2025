document.addEventListener('DOMContentLoaded', () => {
    const storeIdInput = document.getElementById('storeIdInput');
    const triggerReportBtn = document.getElementById('triggerReportBtn');
    const getReportBtn = document.getElementById('getReportBtn');
    const reportIdInput = document.getElementById('reportIdInput');
    const statusArea = document.getElementById('statusArea');

    triggerReportBtn.disabled = false;

    // When the button is clicked generate the report. The button can be clicked with or without a store_id
    triggerReportBtn.addEventListener('click', () => {
        const storeId = storeIdInput.value.trim();
        statusArea.textContent = storeId ? `Triggering report for Store ID: ${storeId}... Please wait.` : `Triggering reports for all stores... Please wait.`;
        statusArea.classList.remove('error');

        const requestBody = storeId ? { store_id: storeId } : {};
        console.log('Sending request to /trigger_report with body:', requestBody);

        fetch('/trigger_report', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json' 
            },
            body: JSON.stringify(requestBody)
        })
            .then(response => {
                console.log('Response status:', response.status);
                console.log('Response headers:', response.headers);

                if (!response.ok) {
                    return response.json().then(errData => {
                        throw new Error(`HTTP error! Status: ${response.status}, ${errData.error || 'Unknown error'} - ${errData.details || ''}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.report_ids) {
                    const reportInfo = data.report_ids.map(r => `Store ID: ${r.store_id}, Report ID: ${r.report_id}`).join('; ');
                    statusArea.textContent = `Reports generated for all stores: ${reportInfo}. Please copy a Report ID to check its status.`;
                    if (data.report_ids.length > 0) {
                        reportIdInput.value = data.report_ids[0].report_id;
                    }
                } else if (data.report_id) {
                    reportIdInput.value = data.report_id;
                    statusArea.textContent = `Report generation started for Store ID ${storeId} with Report ID: ${data.report_id}. Please copy this ID and use "Get Report Status" to check.`;
                } else if (data.error) {
                    statusArea.textContent = `Error triggering report: ${data.error} - ${data.details || ''}`;
                    statusArea.classList.add('error');
                } else {
                    statusArea.textContent = 'Unexpected response from server when triggering report.';
                    statusArea.classList.add('error');
                }
            })
            .catch(error => {
                console.error('Error triggering report:', error);
                statusArea.textContent = `Error triggering report: ${error.message}. Check console for details.`;
                statusArea.classList.add('error');
            });
    });

    // Handle the event where the button is clicked to check the status of the report generation
    getReportBtn.addEventListener('click', () => {
        const reportId = reportIdInput.value.trim();
        if (!reportId) {
            statusArea.textContent = 'Please enter a Report ID.';
            statusArea.classList.add('error');
            return;
        }

        statusArea.textContent = `Fetching status for report ID: ${reportId}...`;
        statusArea.classList.remove('error');

        fetch('/get_report/' + reportId)
            .then(response => {
                if (!response.ok) {
                    if (response.headers.get('Content-Type')?.includes('application/json')) {
                        return response.json().then(errData => {
                            throw new Error(`Report not found or error: ${errData.error || response.status} ${errData.details || ''}`);
                        });
                    }
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                const contentType = response.headers.get('Content-Type');
                if (contentType && contentType.includes('application/json')) {
                    return response.json().then(data => ({ type: 'json', data }));
                } else if (contentType && (
                    contentType.includes('text/csv') ||
                    contentType.includes('application/octet-stream') ||
                    contentType.includes('application/vnd.ms-excel') ||
                    contentType.includes('application/csv')
                )) {
                    return response.blob().then(blob => ({ type: 'csv', blob, reportId }));
                } else {
                    throw new Error(`Unexpected content type: ${contentType}`);
                }
            })
            .then(result => {
                if (result.type === 'json') {
                    const data = result.data;
                    if (data.status === 'Running') {
                        statusArea.textContent = `Report ${reportId} is Running. Please check again in a moment.`;
                    } else if (data.status === 'Error') {
                        statusArea.textContent = `Report ${reportId} processing failed.`;
                        statusArea.classList.add('error');
                    } else if (data.status === 'Complete') {
                        if (data.error) {
                            statusArea.textContent = `Report ${reportId} is Complete, but there was an issue: ${data.error}`;
                            statusArea.classList.add('error');
                        } else {
                            statusArea.textContent = `Report ${reportId} is Complete, but no file was returned.`;
                            statusArea.classList.add('error');
                        }
                    } else {
                        statusArea.textContent = `Unexpected status for report ${reportId}: ${JSON.stringify(data)}`;
                        statusArea.classList.add('error');
                    }
                } else if (result.type === 'csv') {
                    statusArea.textContent = `Report ${reportId} is Complete. Download should start.`;
                    const url = window.URL.createObjectURL(result.blob);
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = url;
                    a.download = result.reportId + '.csv';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                }
            })
            .catch(error => {
                console.error('Error getting report:', error);
                statusArea.textContent = `Error getting report: ${error.message}. Check console for details.`;
                statusArea.classList.add('error');
            });
    });
});