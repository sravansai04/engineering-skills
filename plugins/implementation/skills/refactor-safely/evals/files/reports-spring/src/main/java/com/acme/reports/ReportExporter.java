package com.acme.reports;

import java.util.List;
import java.util.Map;

public interface ReportExporter {
    byte[] export(String reportName, List<Map<String, Object>> rows);
}
