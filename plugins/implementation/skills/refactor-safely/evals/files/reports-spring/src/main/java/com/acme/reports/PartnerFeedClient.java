package com.acme.reports;

import java.util.List;
import java.util.Map;

/** Implemented by the partner-feed adapter, which is deployed with this service. */
public interface PartnerFeedClient {
    List<Map<String, Object>> loadQuarterRows();

    void submit(byte[] document);
}
