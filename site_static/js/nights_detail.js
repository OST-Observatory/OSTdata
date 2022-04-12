let night = {}

$(document).ready(function () {

    //  Load the night info
    let night_id = $('#tag_list').attr('night_id')
    $.ajax({
        url: "/api/nights/" + night_id + '/',
        type: "GET",
        success: function (json) {
            night = json;
            makepage();
        },
        error: function (xhr, errmsg, err) {
            console.log(xhr.status + ": " + xhr.responseText);
        }
    });

    //  Event listeners
    $("#tagEditButton").click(openTagEditBox);


    //  Initializing all dialog windows
    var update_tag_window = $("#tagAdd").dialog({
        autoOpen: false,
        width: 'auto',
        modal: true
    });
});


//  Create the page dynamically
function makepage() {
    show_tags() // handle the tags
}

//
// TAGS
//

//  Check which tags should be displayed in the tag window, and check the
//  included tags in the tag edit window.
function show_tags() {
    $('#tag_list').empty(); // remove all existing tags
    for (i = 0; i < night.tags.length; i++) {
        let tag = night.tags[i];
        $('#tag_pk_' + tag.pk).prop("checked", true);
        $('#tag_list').append(
            "<div class='tag' id='tag-" + tag.pk + "' style='border-color:" + tag.color + "' title='" + tag.info + "'>" + tag.name + "</div>"
        );
    }

}

//  Open window to add/modify/change tags
function openTagEditBox() {
    update_tag_window = $("#tagAdd").dialog({
        buttons: {"Update": update_tags},
        close: function () {
            update_tag_window.dialog("close");
        }
    });

    update_tag_window.dialog("open");
}

// Update the tags attached to this night
function update_tags() {
    let new_tags = $("#tagOptions input:checked").map(
        function () {
            return this.value;
        }).get();
    let night_pk = $('#tagEditButton').attr('night_id')
    $.ajax({
        url: "/api/nights/" + night_pk + '/',
        type: "PATCH",
        contentType: "application/json; charset=utf-8",

        data: JSON.stringify({"tag_ids": new_tags}),

        success: function (json) {
            // update the tags of the star variable, and update the page
            night.tags = json.tags;
            show_tags();
            update_tag_window.dialog("close");
        },

        error: function (xhr, errmsg, err) {
            console.log(xhr.status + ": " + xhr.responseText);
        }
    });
}
