package com.acme.reports;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reports")
public record ReportProperties(String defaultExporter, String quarterlyExporter) {}
