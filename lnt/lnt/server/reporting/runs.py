"""
Report functionality centered around individual runs.
"""

import StringIO
import os

import lnt.server.reporting.analysis
from lnt.db import runinfo

def generate_run_report(run, baseurl, only_html_body = False,
                        num_comparison_runs = 10, result = None):
    """
    generate_run_report(...) -> (str: subject, str: text_report,
                                 str: html_report)

    Generate a comprehensive report on the results of the given individual
    run, suitable for emailing or presentation on a web page.
    """

    assert num_comparison_runs > 0

    ts = run.testsuite
    machine = run.machine
    machine_parameters = machine.parameters
    sri = lnt.server.reporting.analysis.RunInfo(ts)

    # Gather the runs to use for statistical data.
    comparison_window = list(ts.get_previous_runs_on_machine(
            run, num_comparison_runs))

    # Get the specific run to compare to.
    if comparison_window:
        compare_to = comparison_window[0]
    else:
        compare_to = None

    # Get the test names.
    test_names = ts.query(ts.Test.name, ts.Test.id).order_by(ts.Test.name).all()

    # Gather the changes to report, organized by field and then collated by
    # change type.
    primary_fields = list(ts.Sample.get_primary_fields())
    num_total_tests = len(primary_fields) * len(test_names)
    test_results = []
    for field in primary_fields:
        new_failures = []
        new_passes = []
        perf_regressions = []
        perf_improvements = []
        removed_tests = []
        added_tests = []
        existing_failures = []
        unchanged_tests = []
        for name,test_id in test_names:
            cr = sri.get_run_comparison_result(run, compare_to, test_id, field,
                                               comparison_window)
            test_status = cr.get_test_status()
            perf_status = cr.get_value_status()
            if test_status == runinfo.REGRESSED:
                bucket = new_failures
            elif test_status == runinfo.IMPROVED:
                bucket = new_passes
            elif cr.current is None and cr.previous is not None:
                bucket = removed_tests
            elif cr.current is not None and cr.previous is None:
                bucket = added_tests
            elif test_status == runinfo.UNCHANGED_FAIL:
                bucket = existing_failures
            elif perf_status == runinfo.REGRESSED:
                bucket = perf_regressions
            elif perf_status == runinfo.IMPROVED:
                bucket = perf_improvements
            else:
                bucket = unchanged_tests

            bucket.append((name, cr))

        test_results.append(
            (field, (('New Failures', new_failures, False),
                     ('New Passes', new_passes, False),
                     ('Performance Regressions', perf_regressions, True),
                     ('Performance Improvements', perf_improvements, True),
                     ('Removed Tests', removed_tests, False),
                     ('Added Tests', added_tests, False),
                     ('Existing Failures', existing_failures, False),
                     ('Unchanged Tests', unchanged_tests, False))))

    # Collect the simplified results, if desired, for sending back to clients.
    if result is not None:
        pset_results = []
        result['test_results'] = [{ 'pset' : (), 'results' : pset_results}]
        for field,field_results in test_results:
            for _,bucket,_ in field_results:
                for name,cr in bucket:
                    # FIXME: Include additional information about performance
                    # changes.
                    pset_results.append(("%s.%s" % (name, field.name),
                                         cr.get_test_status(),
                                         cr.get_value_status()))

    # Begin report generation...
    subject = """%s test results: %s""" % (
        machine.name, run.start_time.strftime('%Y-%m-%d %H:%M:%S %Z PST'))
    report = StringIO.StringIO()
    html_report = StringIO.StringIO()

    # Generate the report header.
    if baseurl[-1] == '/':
        baseurl = baseurl[:-1]

    report_url = """%s/%d/""" % (baseurl, run.id)
    print >>report, report_url
    print >>report, """Nickname: %s:%d""" % (machine.name, machine.id)
    if 'name' in machine_parameters:
        print >>report, """Name: %s""" % (machine_parameters['name'],)
    print >>report, """Comparing:"""
    # FIXME: Remove hard coded field use here.
    print >>report, """  Run: %d, Order: %s, Start Time: %s, End Time: %s""" % (
        run.id, run.order.llvm_project_revision, run.start_time, run.end_time)
    if compare_to:
        # FIXME: Remove hard coded field use here.
        print >>report, ("""   To: %d, Order: %s, """
                         """Start Time: %s, End Time: %s""") % (
            compare_to.id, compare_to.order.llvm_project_revision,
            compare_to.start_time, compare_to.end_time)
        if run.machine != compare_to.machine:
            print >>report, """*** WARNING ***:""",
            print >>report, """comparison is against a different machine""",
            print >>report, """(%s:%d)""" % (compare_to.machine.name,
                                             compare_to.machine.id)
    else:
        print >>report, """   To: (none)"""
    print >>report

    # Generate the HTML report header.
    print >>html_report, """\
<h1>%s</h1>
<table>""" % subject
    print >>html_report, """\
<tr><td>URL</td><td><a href="%s">%s</a></td></tr>""" % (report_url, report_url)
    print >>html_report, "<tr><td>Nickname</td><td>%s:%d</td></tr>" % (
        machine.name, machine.id)
    if 'name' in machine_parameters:
        print >>html_report, """<tr><td>Name</td><td>%s</td></tr>""" % (
            machine_parameters['name'],)
    print >>html_report, """</table>"""
    print >>html_report, """\
<p>
<table>
  <tr>
    <th>Run</th>
    <th>ID</th>
    <th>Order</th>
    <th>Start Time</th>
    <th>End Time</th>
  </tr>"""
    # FIXME: Remove hard coded field use here.
    print >>html_report, """\
<tr><td>Current</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>""" % (
        run.id, run.order.llvm_project_revision, run.start_time, run.end_time)
    if compare_to:
        # FIXME: Remove hard coded field use here.
        print >>html_report, """\
<tr><td>Previous</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>""" % (
            compare_to.id, compare_to.order.llvm_project_revision,
            compare_to.start_time, compare_to.end_time)
    else:
        print >>html_report, """<tr><td colspan=4>No Previous Run</td></tr>"""
    print >>html_report, """</table>"""
    if compare_to and run.machine != compare_to.machine:
        print >>html_report, """<p><b>*** WARNING ***:""",
        print >>html_report, """comparison is against a different machine""",
        print >>html_report, """(%s:%d)</b></p>""" % (compare_to.machine.name,
                                                      compare_to.machine.id)

    # Generate the summary of the changes.
    total_changes = sum(len(bucket)
                        for _,field_results in test_results
                        for name,bucket,_ in field_results
                        if name != 'Unchanged Tests')

    print >>report, """==============="""
    print >>report, """Tests Summary"""
    print >>report, """==============="""
    print >>report
    print >>html_report, """
<hr>
<h3>Tests Summary</h3>
<table>
<thead><tr><th>Status Group</th><th align="right">#</th></tr></thead>
"""
    # For now, we aggregate across all bucket types for reports.
    for i,(name,_,_) in enumerate(test_results[0][1]):
        num_items = sum(len(field_results[i][1])
                        for _,field_results in test_results)
        if num_items:
                print >>report, '%s: %d' % (name, num_items)
                print >>html_report, """
<tr><td>%s</td><td align="right">%d</td></tr>""" % (
                    name, num_items)
    print >>report, """Total Tests: %d""" % num_total_tests
    print >>report
    print >>html_report, """
<tfoot>
  <tr><td><b>Total Tests</b></td><td align="right"><b>%d</b></td></tr>
</tfoot>
</table>
""" % num_total_tests

    # Finish up the HTML report (wrapping the body, if necessary).
    html_report = html_report.getvalue()
    if not only_html_body:
        # We embed the additional resources, so that the message is self
        # contained.
        static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   "ui", "static")
        style_css = open(os.path.join(static_path,
                                      "style.css")).read()

        html_report = """\
<html>
  <head>
    <style type="text/css">
%(style_css)s
    </style>
    <title>%(subject)s</title>
  </head>
  <body onload="init_report()">
%(html_report)s
  </body>
</html>""" % locals()

    return subject, report.getvalue(), html_report
