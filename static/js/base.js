'use strict';

if (!waitlist) {
	var waitlist = {};
}

waitlist.base = (function(){
	function getMetaData (name) {
		return $('meta[name="'+name+'"]').attr('content');
	}
	
	function displayMessage(message, type, html=false, id=false) {
		var alertHTML = $($.parseHTML(`<div class="alert alert-dismissible alert-${type}" role="alert">
				<button type="button" class="close" data-dismiss="alert" aria-label="Close">
				<span aria-hidden="true">&times;</span>
				</button>
				<p class="text-xs-center"></p>
				</div>`));
		var textContainer = $('.text-xs-center', alertHTML);
		if (id !== false) {
			alertHTML.attr("id", id);
		}
		if (html === true) {
			textContainer.html(message);
		} else {
			textContainer.text(message);
		}
		var alertArea = $('#alert-area-base');
		alertArea.append(alertHTML);
	}

	return {
		getMetaData: getMetaData,
		displayMessage: displayMessage
	};
})();