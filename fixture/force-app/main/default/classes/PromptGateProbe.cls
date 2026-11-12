/**
 * The scratch org experiment ADR-005 points at: runs one version of the Case_Summary template for
 * a list of cases through ConnectApi.EinsteinLLM and returns each response in the shape the gate
 * reads (generations[0].text, prompt, promptTemplateDevName, requestId), one JSON string per case.
 *
 * With isPreview true the call resolves the template and returns the resolved prompt without a
 * model call, which is the step that would settle the merge-field syntax this repository declares
 * rather than verifies (the related list and the retriever). With isPreview false it returns a real
 * generation, which is the step that would replace the stand-in model's summaries with a model's.
 *
 * Uncompiled in this repository (the build environment has no org); the shape of the Connect API
 * classes follows the Apex Reference Guide's EinsteinLLM examples.
 */
public with sharing class PromptGateProbe {

    public static List<String> run(String templateDevName, List<Id> caseIds, Boolean preview) {
        List<String> payloads = new List<String>();
        for (Id caseId : caseIds) {
            ConnectApi.EinsteinPromptTemplateGenerationsInput input = new ConnectApi.EinsteinPromptTemplateGenerationsInput();
            Map<String, ConnectApi.WrappedValue> params = new Map<String, ConnectApi.WrappedValue>();
            ConnectApi.WrappedValue caseValue = new ConnectApi.WrappedValue();
            caseValue.value = new Map<String, String>{ 'id' => caseId };
            params.put('Input:Case', caseValue);
            input.inputParams = params;
            input.isPreview = preview;
            input.additionalConfig = new ConnectApi.EinsteinLlmAdditionalConfigInput();
            input.additionalConfig.applicationName = 'PromptBuilderPreview';

            ConnectApi.EinsteinPromptTemplateGenerationsRepresentation output =
                ConnectApi.EinsteinLLM.generateMessagesForPromptTemplate(templateDevName, input);

            Map<String, Object> payload = new Map<String, Object>();
            List<Object> generations = new List<Object>();
            if (output.generations != null) {
                for (ConnectApi.EinsteinLLMGenerationItemOutput item : output.generations) {
                    generations.add(new Map<String, Object>{ 'text' => item.text, 'responseId' => item.responseId });
                }
            }
            payload.put('generations', generations);
            payload.put('prompt', output.prompt);
            payload.put('promptTemplateDevName', templateDevName);
            payload.put('requestId', output.requestId);
            payload.put('parameters', new Map<String, Object>{ 'Input:Case' => new Map<String, String>{ 'id' => caseId } });
            payload.put('generationErrors', new List<Object>());
            payloads.add(JSON.serializePretty(payload));
        }
        return payloads;
    }
}
