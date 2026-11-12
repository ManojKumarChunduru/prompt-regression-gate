/**
 * The Apex data provider version v3 of Case_Summary names as {!$Apex:CaseSummaryGrounding.Prompt}.
 *
 * Returns the thread facts the template cannot compute from merge fields alone: the comment count
 * and the newest comment date. The offline gate renders the same two facts for the resolved prompt
 * (src/prg/generations.py, render_provider), so the committed prompt and this class agree by
 * construction; ADR-005 states that the class is uncompiled in this repository and names the
 * scratch org step that would run it.
 */
public with sharing class CaseSummaryGrounding {

    public class Request {
        @InvocableVariable(required=true)
        public Case Case;
    }

    public class Response {
        @InvocableVariable
        public String Prompt;
    }

    @InvocableMethod(
        label='Case Summary Grounding'
        description='Thread facts for the Case Summary prompt template'
        CapabilityType='PromptTemplateType://einstein_gpt__fieldCompletion'
    )
    public static List<Response> ground(List<Request> requests) {
        List<Response> responses = new List<Response>();
        for (Request request : requests) {
            List<CaseComment> comments = [
                SELECT Id, CreatedDate
                FROM CaseComment
                WHERE ParentId = :request.Case.Id
                ORDER BY CreatedDate DESC
            ];
            String newest = comments.isEmpty() ? '' : String.valueOf(comments[0].CreatedDate.date());
            Response response = new Response();
            response.Prompt = 'Comment count: ' + comments.size() + '. Newest comment: ' + newest
                + '. Provider: CaseSummaryGrounding.';
            responses.add(response);
        }
        return responses;
    }
}
