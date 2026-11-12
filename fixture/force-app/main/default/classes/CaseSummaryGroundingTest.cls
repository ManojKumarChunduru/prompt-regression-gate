@IsTest
private class CaseSummaryGroundingTest {

    @IsTest
    static void countsCommentsAndNamesTheNewest() {
        Case c = new Case(Subject = 'Aero 2 stops charging', Priority = 'High', Status = 'New');
        insert c;
        insert new CaseComment(ParentId = c.Id, CommentBody = 'Confirmed with the customer.');
        insert new CaseComment(ParentId = c.Id, CommentBody = 'Offered a refund of $240.00.');

        CaseSummaryGrounding.Request request = new CaseSummaryGrounding.Request();
        request.Case = c;
        List<CaseSummaryGrounding.Response> responses = CaseSummaryGrounding.ground(
            new List<CaseSummaryGrounding.Request>{ request }
        );

        System.assertEquals(1, responses.size());
        System.assert(responses[0].Prompt.startsWith('Comment count: 2.'), responses[0].Prompt);
        System.assert(responses[0].Prompt.endsWith('Provider: CaseSummaryGrounding.'), responses[0].Prompt);
    }

    @IsTest
    static void aCaseWithoutCommentsReportsZeroAndAnEmptyDate() {
        Case c = new Case(Subject = 'Orbit Cam drops the wifi', Priority = 'Low', Status = 'New');
        insert c;
        CaseSummaryGrounding.Request request = new CaseSummaryGrounding.Request();
        request.Case = c;
        List<CaseSummaryGrounding.Response> responses = CaseSummaryGrounding.ground(
            new List<CaseSummaryGrounding.Request>{ request }
        );
        System.assertEquals('Comment count: 0. Newest comment: . Provider: CaseSummaryGrounding.', responses[0].Prompt);
    }
}
