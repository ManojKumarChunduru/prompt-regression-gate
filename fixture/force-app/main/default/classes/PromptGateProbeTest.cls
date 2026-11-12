@IsTest
private class PromptGateProbeTest {

    // ConnectApi.EinsteinLLM cannot be called in a test context without a mock the platform does not
    // offer for this class, so the test pins the probe's contract: an empty id list produces an empty
    // payload list and no callout. The shape of a non-empty payload is pinned by the offline gate's
    // reader (tests/test_generations.py), which reads what this class writes.
    @IsTest
    static void anEmptyListProducesNoPayloads() {
        List<String> payloads = PromptGateProbe.run('Case_Summary', new List<Id>(), true);
        System.assertEquals(0, payloads.size());
    }
}
