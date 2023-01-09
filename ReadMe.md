# Most recent updates
I'm not going to put much effort into updating the readme until I'm further along or I notice others are using this or wanting to collaborate. Anything below this section hasn't been updated, but here are the big changes: after generating (you can use batch size > 1 now), the images will go into a queue. Click Next Image in Queue button to see the first image in the Queue on the left side of the screen and then rate it by clicking Vote Left, Can't Decide, or Vote Right. Then click next image in queue to view the next image and repeat. You can also make consecutive generations and they will correctly go into the queue. I haven't tested this on other monitors or with image sizes larger than 512x512 -- not sure if Gradio could misbehave under different parameters.



This is unfinished and cobbled together by someone who doesn't know what they're doing. Use at your own risk. It currently works well if generation parameters are left at default. I haven't done much data validation yet, so leave batch count and batch size at 1 and type things carefully. There's a lot I don't yet know about Python and how Automatic1111 and gradio work, and the resulting code is egregious, even by my standards.

# Using SDRatings

Dump SDRatings.py and the two folders into scripts folder of Automatic1111. Both folders contain editable text files.

Each line in SDRatings is currently in the format:
keywordName(Group1:rating1:numberOfTimesrated1,Group2:rating2)
the last colon and numberofTimesrated is optional and will be assumed to be 0 if missing. SDRatigns will update it the first time the keyword is rated.

ex: Anton Fadeev(Overall:2000:5, ConceptArtist:2200:5, CartoonArtist:1500)

To rate keywords, put keyword (literally type keyword) into your prompt, and put the group names in the rated groups field. When you generate, two keywords that have all groups listed will be selected, and the same prompts will be repeated except keyword will be replaced with keyword1 or keyword2. After generation, you can vote on whether you like left or right better and the ratings will be adjusted. Clicking Can't decide will generate two more sets of images with the same keywords and new seeds. 

AristList.xlsx is an excel spreadsheet that I used to help populate SDRatings.txt since I haven't built in anything for managing this in Automatic1111 yet. 


# Compatible with wildcards script
To use a wildcard, put \_\_NameOfWildCardFile\_\_ into your prompt and a random line from NameOfWildCardFile.txt in wildcards folder will be substituted.

# About Elo Ratings

A higher elo rating is better. With default parameters and a large population, the average rating will be around 1500 and the best of the best (Chess grandmasters and world-class athletes) will be 2600+. I imagine our keyword groups will not be so large that the extremes push out quite so far. 

I used [this article](https://mattmazzola.medium.com/understanding-the-elo-rating-system-264572c7a2b4) for the algorithm and default values for constants.

Something to keep in mind: if we introduce new keywords to the population and remove or stop rating the bad ones, 1500 will eventually become the average active keyword. As long as you keep ratings things, the best will be at the top, but it might be worth keeping in mind that a stale 2000 rating might be equivalent to a recently rated 1800.

# To Do
- Improve code quality if anyone ever wants to collaborate or contribute
- More configurability for elo constants, especially to help fresh keywords and tags find their rating. 
- Let keywords be inserted into negative prompts. 
- Add more messaging to the user through Automatic1111's interface instead of through cmd line
- Add ways to add/remove keywords and groups from within gradio
- Change all instances of group/groups to tag/tags, which might be a more intuitive name
- Have different modes for comparison. Instead of always assigning opponents randomly, have a mode for sorted list. 
  - Randomized (current setting) is good for keywords that are vastly underrated or overrated, but using a sorted list or +- 400 rating points would generally be better.
  - Setting up a round robin -> double elim tournament would be time consuming with a lot of keywords, but might be a good way to build a strong prompt at the same time you're updating ratings.
  - On that note, any mode that will serve another purpose but produce valid comparisons in the end would make updating ratings much less of a chore. 
- Add the keyword to the start of the prompt if "keyword" is not present in the prompt
- Add a mode for rating a new keyword a large number of times against many keywords that already have mature ratings for rating new keywords quickly
- Give credit to the right wildcards script and provide a link. Or upgrade to the newest one if it has more functionality.
- Think about case where one group's is a subset of another group's name
- Output a csv with keywords and tags that can be sorted and/or maybe just a sorted txt file with one keyword + 1 tag
- Think about how to incorporate batch size if at all. Could at least use batch counts to speed up generation. 